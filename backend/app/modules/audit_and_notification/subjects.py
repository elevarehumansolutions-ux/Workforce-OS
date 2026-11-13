"""Say WHAT an audit row was about, in words: "Chidi Okafor (chidi@x.com)", "Sales", "On-time rate".

Every audit row stores what changed (``changes``: an "old" and a "new" snapshot). Most of the time
that already holds the name, so the label is read from it and needs no extra lookup. For rows that
only stored the changed fields (a rename's old value, a weight) the repository looks the current
name up instead (``AuditRepository.get_subject_labels``). Pure functions only, easy to test.
"""

# The snapshot field that names each kind of thing, in the order they are tried.
NAME_FIELDS = {
    "department": ["name"],
    "position": ["title"],
    "location": ["name"],
    "kpi": ["name"],
    "okr": ["title"],
    "key_result": ["description"],
    "task": ["title"],
    "workflow_template": ["name"],
    "blueprint_item": ["title"],
}


def _employee_label(snapshot: dict) -> str | None:
    """"Chidi Okafor (chidi@x.com)": the name and the email, whichever the snapshot has."""
    first = snapshot.get("first_name")
    last = snapshot.get("last_name")
    name = " ".join(part for part in (first, last) if part)
    email = snapshot.get("work_email")
    if name and email:
        return f"{name} ({email})"
    return name or email or None


def label_from_snapshot(entity_type: str, snapshot: dict | None) -> str | None:
    """The label for one snapshot ("old" or "new") of an entity, or None if it has no name in it."""
    if not isinstance(snapshot, dict):
        return None
    if entity_type == "employee":
        return _employee_label(snapshot)
    if entity_type == "invite":
        return snapshot.get("email")
    if entity_type == "membership":
        return snapshot.get("email")
    for field in NAME_FIELDS.get(entity_type, []):
        value = snapshot.get(field)
        if value:
            return str(value)
    return None


def label_from_changes(entity_type: str, changes: dict | None) -> str | None:
    """The label stored in an audit row's ``changes``: the "new" side first, then the "old" side."""
    if not isinstance(changes, dict):
        return None
    return label_from_snapshot(entity_type, changes.get("new")) or label_from_snapshot(
        entity_type, changes.get("old")
    )
