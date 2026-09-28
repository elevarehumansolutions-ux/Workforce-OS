"""Text-normalization SQL helpers shared across modules."""

from sqlalchemy import func, text


def normalized_name_expr(value):
    """Build the SQL expression that derives a comparison key from free text.

    Unicode NFKC, trimmed, internal whitespace collapsed, lowercased — so
    "Customer Success", "  customer   SUCCESS " and a non-breaking-space
    variant all compare equal. Defined once and used both for generated
    columns' DDL and for any query comparing against a candidate name, so
    the write side and the read side can never drift apart.

    Args:
        value: A SQL expression (a column, or a bound/cast parameter)
            holding the free text to normalize.

    Returns:
        A SQL expression producing the normalized text.
    """
    return func.lower(
        func.regexp_replace(
            func.btrim(func.normalize(value, text("NFKC"))),
            r"\s+",
            " ",
            "g",
        )
    )
