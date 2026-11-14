"""The task email's content: a task title is typed by a person, so it must not be able to inject HTML."""
import pytest

from app.core.email import ResendEmailService


@pytest.mark.asyncio
async def test_html_in_a_task_title_is_escaped_and_the_link_is_present():
    sent = {}

    async def fake_send(subject, recipients, html_body):
        sent.update(subject=subject, recipients=recipients, html=html_body)

    # Skip the real constructor (it needs the Resend key); only the content is under test.
    service = object.__new__(ResendEmailService)
    service._send_html = fake_send

    await service.send_task_email(
        "chidi@example.com",
        'New task: <script>alert("x")</script>',
        "A task for <b>Dispatch</b> has been assigned to you.",
        "https://app.example.com/tasks/123",
    )

    assert sent["recipients"] == ["chidi@example.com"]
    assert "<script>" not in sent["html"]
    assert "&lt;script&gt;" in sent["html"]
    assert "<b>Dispatch</b>" not in sent["html"]
    assert "https://app.example.com/tasks/123" in sent["html"]
