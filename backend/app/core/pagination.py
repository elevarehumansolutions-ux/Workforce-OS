"""Cursor-based and offset-based pagination utilities.

Public interface:
- ``encode_cursor`` / ``decode_cursor``: opaque base64 cursor helpers.
- ``paginate_cursor``: keyset pagination for large, append-heavy result sets.
- ``paginate``: classic page/limit offset pagination.
- ``PageParams``: Pydantic model for page/limit query parameters.
"""

import base64
import math
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Select, and_, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationException
from app.core.schemas import PaginationMeta, PaginationResponse


def encode_cursor(created_at: datetime, id: UUID, sort_value: float | None = None) -> str:
    """Encode (created_at, id) — plus an optional secondary sort value — into a cursor.

    ``sort_value`` is only meaningful when the query was paginated with an extra
    ``sort_column`` (see ``paginate_cursor``); callers that don't use one simply
    never read it back out.
    """
    sort_value_str = "" if sort_value is None else repr(sort_value)
    raw = f"{sort_value_str}:{created_at.isoformat()}:{str(id)}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[float | None, datetime, UUID]:
    """Decode a base64 URL-safe cursor string into (sort_value, created_at, id).

    Raises:
        ValidationException: If the cursor string is malformed or cannot be decoded.

    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        sort_value_str, rest = raw.split(":", 1)
        # rsplit from the right once — datetime contains colons too
        created_at_str, id_str = rest.rsplit(":", 1)
        created_at = datetime.fromisoformat(created_at_str)
        sort_value = float(sort_value_str) if sort_value_str else None
        return sort_value, created_at, UUID(id_str)
    except Exception as exc:
        raise ValidationException(message="Invalid pagination cursor") from exc


async def paginate_cursor(
    query: Select,
    session: AsyncSession,
    model: type,
    cursor: str | None = None,
    limit: int = 20,
    sort_column: str | None = None,
) -> dict:
    """Paginate a query using cursor-based (keyset) pagination.

    Args:
        query: The base SQLAlchemy SELECT statement (without ORDER BY or LIMIT).
        session: The async database session.
        model: The ORM-mapped class being paginated. ``created_at``/``id``/
            ``sort_column`` are resolved from this class explicitly rather
            than inferred from ``query``'s FROM clause — inferring them
            breaks (wrong table, or an ambiguous-column error) the moment
            ``query`` includes a JOIN, since a joined query's FROM no
            longer maps 1:1 to a single table's columns.
        cursor: Opaque cursor string from the previous page, or None for the first page.
        limit: Number of items per page (default 20, max 100).
        sort_column: Optional name of a nullable numeric column to sort by (DESC,
            NULLS LAST) ahead of the default created_at/id ordering — e.g. "ai_score".
            When given, the keyset filter and cursor stay consistent with that
            ordering across pages; when omitted, behavior is unchanged (created_at
            desc, id desc).

    Returns:
        A dict with ``items``, ``next_cursor``, ``count`` (page size), and ``total``
        (total matching rows across all pages).

    """
    # Run a COUNT(*) on the unfiltered-by-cursor base query so we always
    # return the total number of matching rows regardless of which page we're on.
    count_query = select(func.count()).select_from(query.subquery())
    total: int = (await session.scalar(count_query)) or 0

    created_at_col = model.created_at
    id_col = model.id
    sort_col = getattr(model, sort_column) if sort_column else None

    if cursor:
        last_sort_value, created_at, last_id = decode_cursor(cursor)
        if sort_col is not None:
            if last_sort_value is None:
                # Cursor is already in the NULLS-LAST tail: stay there.
                query = query.where(
                    and_(
                        sort_col.is_(None),
                        tuple_(created_at_col, id_col) < tuple_(created_at, last_id),
                    )
                )
            else:
                query = query.where(
                    or_(
                        # NULLS LAST means every null-sort_col row sorts after
                        # every non-null one — once the cursor is past the
                        # last non-null row, all null rows are always "next",
                        # regardless of their created_at/id. Without this,
                        # `sort_col < value` and `sort_col == value` both
                        # evaluate to NULL (never true) for a null sort_col,
                        # so the entire NULLS-LAST tail becomes unreachable.
                        sort_col.is_(None),
                        sort_col < last_sort_value,
                        and_(
                            sort_col == last_sort_value,
                            tuple_(created_at_col, id_col) < tuple_(created_at, last_id),
                        ),
                    )
                )
        else:
            # Keyset filter: rows older than the cursor position
            query = query.where(
                tuple_(created_at_col, id_col) < tuple_(created_at, last_id)
            )

    order_cols = [sort_col.desc().nulls_last()] if sort_col is not None else []
    order_cols += [created_at_col.desc(), id_col.desc()]

    # Fetch one extra item to detect whether a next page exists
    query = query.order_by(*order_cols).limit(limit + 1)

    result = await session.execute(query)
    items = result.scalars().all()

    has_next = len(items) > limit
    if has_next:
        items = items[:limit]

    next_cursor = None
    if has_next and items:
        last = items[-1]
        last_sort_value = getattr(last, sort_column) if sort_column else None
        next_cursor = encode_cursor(last.created_at, last.id, last_sort_value)

    return {
        "items": items,
        "next_cursor": next_cursor,
        "count": len(items),
        "total": total,
    }


class PageParams(BaseModel):
    """Query parameters for offset-based pagination endpoints."""

    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)


async def paginate(
    query: Select,
    page: int,
    limit: int,
    session: AsyncSession,
) -> PaginationResponse:
    """Paginate a query using classic page/limit offset pagination.

    Args:
        query: The base SQLAlchemy SELECT statement.
        page: 1-based page number.
        limit: Number of items per page.
        session: The async database session.

    Returns:
        A ``PaginationResponse`` containing the items and pagination metadata.

    """
    offset = (page - 1) * limit

    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.scalar(count_query)) or 0

    result = await session.execute(query.offset(offset).limit(limit))
    items = result.scalars().all()

    total_pages = math.ceil(total / limit) if total > 0 else 1

    return PaginationResponse(
        message="OK",
        data=items,
        pagination=PaginationMeta(
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        ),
    )
