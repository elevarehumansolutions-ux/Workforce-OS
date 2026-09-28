"""Grounding: keep Claude's answers pointed at things that exist."""

import logging
import uuid
from collections.abc import Mapping, Sequence


from .llm import LLMOutputError
from .schemas import ResolvedHandles


logger = logging.getLogger(__name__)

def make_handles(ids: Sequence[uuid.UUID], prefix: str) -> dict[str, uuid.UUID]:
    """Label real ids with short handles (P1...Pn) to show Claude instead of UUIDs."""
    return {f"{prefix}{number}": real_id for number, real_id in enumerate(ids, start=1)}


def resolve_handles(
    picked: Sequence[str],
    handles: Mapping[str, uuid.UUID],
) -> ResolvedHandles:
    """Translate Claude's picked handles back to real ids, dropping invented ones.

    A handle we never handed out is dropped, not an error: the reviewer
    is the safety net and a missed suggestion is cheap. But if more than
    half of what Claude picked is invented, the run is treated as failed -
    that points at a broken prompt, not a stray typo.

    Raises:
        LLMOutputError: More than half of the picked handles don't exist.
    """
    ids: list[uuid.UUID] = []
    dropped: list[str] = []
    for raw in picked:
        real_id = handles.get(normalize_handle(raw))
        if real_id is None:
            dropped.append(raw)
        elif real_id not in ids:
            ids.append(real_id)
    
    if dropped:
        logger.warning(
            "Dropped %d invented handle(s): %s",
            len(dropped), dropped
        )
    
    if len(dropped) * 2 > len(picked):
        raise LLMOutputError(
            f"{len(dropped)} of {len(picked)} picked handles do not exist"
        )
    
    return ResolvedHandles(ids=ids, dropped=dropped)

def normalize_handle(raw: str) -> str:
    """Canonical form of a handle CLaude wrote: ' p2 ' -> 'P2'."""
    return raw.strip().upper()
    
