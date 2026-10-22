"""The facts about one task that the Scoring module needs, in a plain shape.

The Scoring module (M12) marks each task on time, late or not done. To do that
it needs a few facts about the task and about its blocks, but it must not reach
into the Task module's tables itself. The Task module hands it a list of these
rows instead (``TaskService.list_tasks_for_scoring``).
"""


class TaskForScoring:
    """One task, as the Scoring module sees it.

    Attributes:
        task_id: The task's id.
        department_id: The department that does the work.
        kpi_id: The KPI the task is linked to, or None.
        assigned_to_employee_id: Who holds the task now, or None (nobody).
        status: ``open``, ``in_progress``, ``completed`` or ``cancelled``.
        due_at: The written deadline.
        completed_at: When it was completed, or None.
        approved_blocked_seconds: Blocked time a reviewer approved.
        has_pending_block: True if any block of this task is still waiting
            for a reviewer's decision (an open block counts: it starts pending).
        last_block_reviewed_at: When the most recent block was reviewed, or None.
    """

    def __init__(
        self,
        task_id,
        department_id,
        kpi_id,
        assigned_to_employee_id,
        status,
        due_at,
        completed_at,
        approved_blocked_seconds,
        has_pending_block,
        last_block_reviewed_at,
    ):
        """Store the facts."""
        self.task_id = task_id
        self.department_id = department_id
        self.kpi_id = kpi_id
        self.assigned_to_employee_id = assigned_to_employee_id
        self.status = status
        self.due_at = due_at
        self.completed_at = completed_at
        self.approved_blocked_seconds = approved_blocked_seconds
        self.has_pending_block = has_pending_block
        self.last_block_reviewed_at = last_block_reviewed_at
