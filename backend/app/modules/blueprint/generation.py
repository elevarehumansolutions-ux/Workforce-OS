"""Generate a blueprint: ask Claude, then check every part of its answer before saving.

Claude's answer is treated as untrusted. Labels we never gave it are dropped,
a proposal that the company already has is pointed at the real row instead of
being proposed again, and a reporting loop is cut. Nothing here creates a real
department, position or OKR: it only saves pending items for HR to review.
"""

import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.enums import AIUsagePurpose, ModelTier
from app.modules.ai.grounding import make_handles, normalize_handle
from app.modules.ai.llm import generate_structured
from app.modules.ai.prompts import BusinessContext
from app.modules.business_dna.repository import BusinessDNARepository
from app.modules.kpis.repository import KPIRepository
from app.modules.okrs.repository import OKRRepository

from .enums import BlueprintKind
from .models import BlueprintItem
from .prompts import (
    MAX_DEPARTMENTS,
    MAX_KEY_RESULTS_PER_OBJECTIVE,
    MAX_KPIS,
    MAX_KPIS_PER_DEPARTMENT,
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


def normalize_weights(raw: list[float], budget: Decimal) -> list[Decimal]:
    """Scale proposed KPI weights so they add up to exactly ``budget`` (2 decimals).

    Claude's arithmetic is not trusted: a department's weights may not exceed 100%
    (and an existing department may already use some of it), so they are always
    rescaled. A negative or missing weight counts as 0; if every weight is 0 the
    budget is split equally. Any rounding leftover goes on the first KPI.
    """
    weights = [max(w, 0.0) if w == w else 0.0 for w in raw]  # w == w is False for NaN
    total = sum(weights)
    if total <= 0:
        weights = [1.0] * len(weights)
        total = float(len(weights))
    scaled = [
        (Decimal(str(w)) / Decimal(str(total)) * budget).quantize(Decimal("0.01"), ROUND_HALF_UP)
        for w in weights
    ]
    scaled[0] += budget - sum(scaled)
    return scaled


def _target_value(value: float | None) -> Decimal | None:
    """A KPI target as a Decimal that fits the column; None if missing or absurd."""
    if value is None or value != value or abs(value) >= 1e11:
        return None
    return Decimal(str(round(value, 2)))


def build_item_rows(
    answer: BlueprintAnswer,
    *,
    organization_id: uuid.UUID,
    batch_id: uuid.UUID,
    known: KnownStructure,
    department_names: dict[uuid.UUID, str],
    position_names: dict[uuid.UUID, tuple[str, uuid.UUID]],
    existing_objective_titles: set[str],
    kpi_room: dict[uuid.UUID, Decimal] | None = None,
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
        kpi_room: For an existing department, how much of its 100% KPI weight is
            still free. A department not in the map has all 100 free.
    """
    rows: list[dict] = []
    kpi_room = kpi_room or {}
    # Every row's ref must be unique in the batch whatever its kind (a database
    # rule), so Claude reusing "P1" for a department and a position cannot crash the save.
    used_refs: set[str] = set()

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
        taken = ref in known.new_department_refs or ref in known.department_alias or ref in used_refs
        if not ref or not name or taken or ref in known.existing_department_ids:
            continue
        already_there = existing_department_by_name.get(name_key(name))
        if already_there is not None:
            # The company has it already: later items that use this ref attach to the real row.
            known.department_alias[ref] = already_there
            continue
        known.new_department_refs.add(ref)
        used_refs.add(ref)
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
        taken = ref in known.new_position_refs or ref in known.position_alias or ref in used_refs
        if not ref or not title or place is None or taken or ref in known.existing_position_ids:
            continue
        department_id, department_ref = place
        if department_id is not None:
            already_there = existing_position_by_key.get((name_key(title), department_id))
            if already_there is not None:
                known.position_alias[ref] = already_there
                continue
        known.new_position_refs.add(ref)
        used_refs.add(ref)
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
    seen_titles = set(existing_objective_titles)
    kept_key_result_refs: set[str] = set()
    for proposed in answer.objectives[:MAX_OBJECTIVES]:
        ref = normalize_handle(proposed.ref)
        title = clean_text(proposed.title, _TITLE_LIMIT)
        if not ref or not title or ref in used_refs or name_key(title) in seen_titles:
            continue
        department_id, department_ref = None, None
        if proposed.department:
            place = known.find_department(proposed.department)
            if place is None:
                continue
            department_id, department_ref = place
        used_refs.add(ref)
        seen_titles.add(name_key(title))
        add_row(
            BlueprintKind.OBJECTIVE.value,
            title,
            clean_text(proposed.rationale, _RATIONALE_LIMIT),
            ref=ref,
            department_id=department_id,
            department_ref=department_ref,
        )
        usable = [k for k in proposed.key_results if clean_text(k.description, _TITLE_LIMIT)]
        for key_result in usable[:MAX_KEY_RESULTS_PER_OBJECTIVE]:
            key_result_ref = normalize_handle(key_result.ref)
            # A blank or reused ref only costs the KPI link, never the key result itself.
            if not key_result_ref or key_result_ref in used_refs:
                key_result_ref = None
            else:
                used_refs.add(key_result_ref)
                kept_key_result_refs.add(key_result_ref)
            add_row(
                BlueprintKind.KEY_RESULT.value,
                clean_text(key_result.description, _TITLE_LIMIT),
                "Measures the objective above.",
                ref=key_result_ref,
                objective_ref=ref,
            )

    # --- KPIs, per department ---------------------------------------------------
    # Group first, so each department's weights can be rescaled together.
    kpis_by_department: dict[str, list] = {}
    department_of_group: dict[str, tuple[uuid.UUID | None, str | None]] = {}
    for proposed in answer.kpis[:MAX_KPIS]:
        name = clean_text(proposed.name, _TITLE_LIMIT)
        place = known.find_department(proposed.department)
        if not name or place is None:
            continue
        group_key = str(place[0]) if place[0] is not None else "ref:" + str(place[1])
        group = kpis_by_department.setdefault(group_key, [])
        if len(group) >= MAX_KPIS_PER_DEPARTMENT:
            continue
        group.append(proposed)
        department_of_group[group_key] = place

    for group_key, group in kpis_by_department.items():
        department_id, department_ref = department_of_group[group_key]
        room = Decimal(100)
        if department_id is not None:
            room = kpi_room.get(department_id, Decimal(100))
        if room <= 0:
            continue
        weights = normalize_weights([k.weight for k in group], room)
        for proposed, weight in zip(group, weights):
            linked = normalize_handle(proposed.key_result or "")
            add_row(
                BlueprintKind.KPI.value,
                clean_text(proposed.name, _TITLE_LIMIT),
                clean_text(proposed.rationale, _RATIONALE_LIMIT),
                department_id=department_id,
                department_ref=department_ref,
                key_result_ref=linked if linked in kept_key_result_refs else None,
                kpi_weight=weight,
                kpi_target_value=_target_value(proposed.target_value),
                kpi_unit=clean_text(proposed.unit, 40) or None,
                kpi_is_inverse=bool(proposed.lower_is_better),
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

    # How much of each existing department's 100% KPI weight is still free.
    kpi_repo = KPIRepository(db)
    kpi_room: dict[uuid.UUID, Decimal] = {}
    for department in departments:
        used = await kpi_repo.sum_weights_for_group(department.id)
        kpi_room[department.id] = max(Decimal(100) - used, Decimal(0))
    full_departments = [
        handle_of_department[i] for i, room in kpi_room.items() if room <= 0
    ]

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
        full_departments,
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
        kpi_room=kpi_room,
    )
    if not rows:
        return []
    return await repo.create_items(rows)
