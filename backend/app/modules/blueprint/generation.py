"""Generate a blueprint: ask Claude, then check every part of its answer before saving.

Claude's answer is treated as untrusted. Labels we never gave it are dropped,
a proposal that the company already has is pointed at the real row instead of
being proposed again, and a reporting loop is cut. Nothing here creates a real
department, position or OKR: it only saves pending items for HR to review.
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.enums import AIUsagePurpose, ModelTier
from app.modules.ai.grounding import make_handles, normalize_handle
from app.modules.ai.llm import generate_structured
from app.modules.ai.prompts import BusinessContext
from app.modules.business_dna.repository import BusinessDNARepository
from app.modules.okrs.repository import OKRRepository

from .enums import BlueprintKind
from .models import BlueprintItem
from .prompts import (
    MAX_DEPARTMENTS,
    MAX_KEY_RESULTS_PER_OBJECTIVE,
    MAX_OBJECTIVES,
    MAX_POSITIONS,
    ExistingDepartment,
    ExistingPosition,
    blueprint_system_prompt,
    build_blueprint_prompt,
)
from .repository import BlueprintRepository
from .schemas import BlueprintAnswer

logger = logging.getLogger(__name__)

MAX_CLEANUPS = 15
_MAX_REPORTING_DEPTH = 15
_TITLE_LIMIT = 300
_RATIONALE_LIMIT = 1000


def clean_text(value: str | None, limit: int) -> str:
    """Trim whitespace and cut to a sane length; None becomes an empty string."""
    return (value or "").strip()[:limit]


def name_key(value: str) -> str:
    """Comparison form of a name: 'Human  Resources ' and 'human resources' match."""
    return " ".join(value.lower().split())


class KnownStructure:
    """What the company has now, plus what this answer is adding, for looking labels up.

    A label can mean three things: an existing row (``ED1``/``EP1``), a new
    item of this batch (``D1``/``P1``), or a new item that turned out to be
    something the company already has (an *alias*, treated as the existing row).
    """

    def __init__(self) -> None:
        """Start empty; ``generate_blueprint`` fills it."""
        self.existing_department_ids: dict[str, uuid.UUID] = {}
        self.existing_position_ids: dict[str, uuid.UUID] = {}
        self.new_department_refs: set[str] = set()
        self.new_position_refs: set[str] = set()
        self.department_alias: dict[str, uuid.UUID] = {}
        self.position_alias: dict[str, uuid.UUID] = {}

    def find_department(self, raw: str | None) -> tuple[uuid.UUID | None, str | None] | None:
        """Turn a department label into (real id, None) or (None, new ref); None if unknown."""
        label = normalize_handle(raw or "")
        if label in self.existing_department_ids:
            return self.existing_department_ids[label], None
        if label in self.department_alias:
            return self.department_alias[label], None
        if label in self.new_department_refs:
            return None, label
        return None

    def find_position(self, raw: str | None) -> tuple[uuid.UUID | None, str | None] | None:
        """Same as ``find_department`` but for positions."""
        label = normalize_handle(raw or "")
        if label in self.existing_position_ids:
            return self.existing_position_ids[label], None
        if label in self.position_alias:
            return self.position_alias[label], None
        if label in self.new_position_refs:
            return None, label
        return None


def _cut_reporting_loops(boss_of: dict[str, str]) -> None:
    """Remove ``reports_to`` links that lead back to the same position.

    ``boss_of`` maps a new position's ref to its new boss's ref. Walk up from
    each position; if we come back to where we started (or climb too long),
    that position loses its boss, which makes it a top of the chart.
    """
    for start in list(boss_of):
        current = start
        for _ in range(_MAX_REPORTING_DEPTH):
            current = boss_of.get(current)
            if current is None:
                break
            if current == start:
                del boss_of[start]
                break
        else:
            boss_of.pop(start, None)


def build_item_rows(
    answer: BlueprintAnswer,
    *,
    organization_id: uuid.UUID,
    batch_id: uuid.UUID,
    known: KnownStructure,
    department_names: dict[uuid.UUID, str],
    position_names: dict[uuid.UUID, tuple[str, uuid.UUID]],
    existing_objective_titles: set[str],
) -> list[dict]:
    """Turn Claude's answer into rows ready to save. Pure: no database, no API.

    Args:
        answer: What Claude replied.
        organization_id: Owner of every row.
        batch_id: Shared by every row of this run.
        known: Existing labels; this function adds the new refs it accepts.
        department_names: Existing department id -> name.
        position_names: Existing position id -> (title, department id).
        existing_objective_titles: Normalised titles of OKRs the company has.
    """
    rows: list[dict] = []

    def add_row(kind: str, title: str, rationale: str, **extra) -> None:
        rows.append(
            {
                "organization_id": organization_id,
                "batch_id": batch_id,
                "kind": kind,
                "sort_order": len(rows),
                "title": title,
                "rationale": rationale or "Suggested from your Business DNA.",
                **extra,
            }
        )

    existing_department_by_name = {name_key(n): i for i, n in department_names.items()}

    # --- departments -------------------------------------------------------
    for proposed in answer.departments[:MAX_DEPARTMENTS]:
        ref = normalize_handle(proposed.ref)
        name = clean_text(proposed.name, _TITLE_LIMIT)
        taken = ref in known.new_department_refs or ref in known.department_alias
        if not ref or not name or taken or ref in known.existing_department_ids:
            continue
        already_there = existing_department_by_name.get(name_key(name))
        if already_there is not None:
            # The company has it already: later items that use this ref attach to the real row.
            known.department_alias[ref] = already_there
            continue
        known.new_department_refs.add(ref)
        add_row(
            BlueprintKind.DEPARTMENT.value,
            name,
            clean_text(proposed.rationale, _RATIONALE_LIMIT),
            ref=ref,
        )

    # --- positions, pass 1: which ones are kept and where they sit ----------
    existing_position_by_key = {
        (name_key(title), dept_id): pos_id
        for pos_id, (title, dept_id) in position_names.items()
    }
    kept_positions = []  # (proposal, ref, title, department_id, department_ref)
    for proposed in answer.positions[:MAX_POSITIONS]:
        ref = normalize_handle(proposed.ref)
        title = clean_text(proposed.title, _TITLE_LIMIT)
        place = known.find_department(proposed.department)
        taken = ref in known.new_position_refs or ref in known.position_alias
        if not ref or not title or place is None or taken or ref in known.existing_position_ids:
            continue
        department_id, department_ref = place
        if department_id is not None:
            already_there = existing_position_by_key.get((name_key(title), department_id))
            if already_there is not None:
                known.position_alias[ref] = already_there
                continue
        known.new_position_refs.add(ref)
        kept_positions.append((proposed, ref, title, department_id, department_ref))

    # --- positions, pass 2: who reports to whom (the organogram) -------------
    boss_ref_of: dict[str, str] = {}
    boss_id_of: dict[str, uuid.UUID] = {}
    for proposed, ref, _, _, _ in kept_positions:
        boss = known.find_position(proposed.reports_to)
        if boss is None:
            continue
        boss_id, boss_ref = boss
        if boss_ref == ref:
            continue
        if boss_id is not None:
            boss_id_of[ref] = boss_id
        else:
            boss_ref_of[ref] = boss_ref
    _cut_reporting_loops(boss_ref_of)

    for proposed, ref, title, department_id, department_ref in kept_positions:
        add_row(
            BlueprintKind.POSITION.value,
            title,
            clean_text(proposed.rationale, _RATIONALE_LIMIT),
            ref=ref,
            department_id=department_id,
            department_ref=department_ref,
            reports_to_position_id=boss_id_of.get(ref),
            reports_to_ref=boss_ref_of.get(ref),
        )

    # --- objectives and their key results ------------------------------------
    used_objective_refs: set[str] = set()
    seen_titles = set(existing_objective_titles)
    for proposed in answer.objectives[:MAX_OBJECTIVES]:
        ref = normalize_handle(proposed.ref)
        title = clean_text(proposed.title, _TITLE_LIMIT)
        if not ref or not title or ref in used_objective_refs or name_key(title) in seen_titles:
            continue
        department_id, department_ref = None, None
        if proposed.department:
            place = known.find_department(proposed.department)
            if place is None:
                continue
            department_id, department_ref = place
        used_objective_refs.add(ref)
        seen_titles.add(name_key(title))
        add_row(
            BlueprintKind.OBJECTIVE.value,
            title,
            clean_text(proposed.rationale, _RATIONALE_LIMIT),
            ref=ref,
            department_id=department_id,
            department_ref=department_ref,
        )
        key_results = [clean_text(k, _TITLE_LIMIT) for k in proposed.key_results]
        for description in [k for k in key_results if k][:MAX_KEY_RESULTS_PER_OBJECTIVE]:
            add_row(
                BlueprintKind.KEY_RESULT.value,
                description,
                "Measures the objective above.",
                objective_ref=ref,
            )

    # --- clean-ups of what already exists ("sanitize") ---------------------------
    for cleanup in answer.cleanups[:MAX_CLEANUPS]:
        label = normalize_handle(cleanup.target)
        note = clean_text(cleanup.note, _RATIONALE_LIMIT)
        new_name = clean_text(cleanup.new_name, _TITLE_LIMIT)
        if label in known.existing_department_ids:
            target_id = known.existing_department_ids[label]
            current = department_names[target_id]
            kind_if_rename = BlueprintKind.RENAME_DEPARTMENT.value
            target_column = "department_id"
        elif label in known.existing_position_ids:
            target_id = known.existing_position_ids[label]
            current = position_names[target_id][0]
            kind_if_rename = BlueprintKind.RENAME_POSITION.value
            target_column = "position_id"
        else:
            continue
        if cleanup.action == "rename" and new_name and name_key(new_name) != name_key(current):
            add_row(kind_if_rename, new_name, note or f"Rename '{current}'.", **{target_column: target_id})
        elif note:
            add_row(
                BlueprintKind.REVIEW_NOTE.value,
                f"Check: {current}",
                note,
                **{target_column: target_id},
            )

    return rows


async def generate_blueprint(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[BlueprintItem]:
    """Propose a blueprint for one organization and save it as pending items.

    Does nothing (returns ``[]``) when items already wait for review, or when
    the Business DNA says too little to design anything from.
    Never commits; the caller owns the transaction.
    """
    repo = BlueprintRepository(db)
    if await repo.has_pending_items(organization_id):
        return []

    dna = await BusinessDNARepository(db).get_business_dna_by_organization_id(organization_id)
    if dna is None or not (dna.industry or dna.products_services_description):
        return []
    business = BusinessContext(
        industry=dna.industry,
        products_services=dna.products_services_description,
        revenue_drivers=dna.revenue_drivers,
        operational_drivers=dna.operational_drivers,
        customer_value_drivers=dna.customer_value_drivers,
    )

    departments = await repo.list_existing_departments()
    positions = await repo.list_existing_positions()

    known = KnownStructure()
    known.existing_department_ids = make_handles([d.id for d in departments], "ED")
    known.existing_position_ids = make_handles([p.id for p in positions], "EP")
    handle_of_department = {i: h for h, i in known.existing_department_ids.items()}
    handle_of_position = {i: h for h, i in known.existing_position_ids.items()}

    prompt = build_blueprint_prompt(
        business,
        [ExistingDepartment(handle_of_department[d.id], d.name) for d in departments],
        [
            ExistingPosition(
                handle_of_position[p.id],
                p.title,
                handle_of_department.get(p.department_id, "?"),
                handle_of_position.get(p.reports_to_position_id),
            )
            for p in positions
        ],
    )
    answer = await generate_structured(
        db,
        organization_id=organization_id,
        # An existing purpose on purpose: ai_usage_log has a database check on it,
        # and widening that would mean changing the AI module.
        purpose=AIUsagePurpose.AI_SUGGESTION_GENERATION,
        tier=ModelTier.STRONG,
        system=blueprint_system_prompt(),
        prompt=prompt,
        output_type=BlueprintAnswer,
        max_tokens=16000,
    )

    objective_titles = await OKRRepository(db).list_active_objective_titles(organization_id)
    rows = build_item_rows(
        answer,
        organization_id=organization_id,
        batch_id=uuid.uuid4(),
        known=known,
        department_names={d.id: d.name for d in departments},
        position_names={p.id: (p.title, p.department_id) for p in positions},
        existing_objective_titles={name_key(t) for t in objective_titles},
    )
    if not rows:
        return []
    return await repo.create_items(rows)
