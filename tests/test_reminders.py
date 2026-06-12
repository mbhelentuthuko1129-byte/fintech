from datetime import date, datetime

from app.services.reminders import format_reminder_message, is_reminder_due

TODAY = date(2026, 6, 10)


def due(**overrides) -> bool:
    base = {
        "status": "scheduled",
        "due_date": date(2026, 6, 1),
        "send_count": 0,
        "last_sent_at": None,
        "today": TODAY,
        "cadence_days": 3,
        "max_sends": 3,
    }
    base.update(overrides)
    return is_reminder_due(**base)


class TestIsReminderDue:
    def test_overdue_never_sent(self):
        assert due()

    def test_due_today(self):
        assert due(due_date=TODAY)

    def test_not_yet_due(self):
        assert not due(due_date=date(2026, 6, 15))

    def test_paid_is_never_due(self):
        assert not due(status="paid")

    def test_cancelled_is_never_due(self):
        assert not due(status="cancelled")

    def test_sent_status_still_eligible_for_follow_up(self):
        assert due(status="sent", send_count=1, last_sent_at=datetime(2026, 6, 1, 9, 0))

    def test_cadence_not_elapsed(self):
        assert not due(send_count=1, last_sent_at=datetime(2026, 6, 9, 9, 0))

    def test_cadence_exactly_elapsed(self):
        assert due(send_count=1, last_sent_at=datetime(2026, 6, 7, 9, 0))

    def test_max_sends_reached(self):
        assert not due(send_count=3, last_sent_at=datetime(2026, 6, 1, 9, 0))


class TestFormatReminderMessage:
    def test_first_reminder(self):
        msg = format_reminder_message("Acme", "Thabo", 1500.0, date(2026, 6, 1), "INV-9", 0)
        assert "Hi Thabo," in msg
        assert "friendly reminder" in msg
        assert "ZAR 1,500.00" in msg
        assert "INV-9" in msg

    def test_follow_up_numbering(self):
        msg = format_reminder_message("Acme", "Thabo", 1500.0, date(2026, 6, 1), None, 2)
        assert "follow-up 3" in msg

    def test_no_customer_name(self):
        msg = format_reminder_message("Acme", None, 50.0, date(2026, 6, 1), None, 0)
        assert msg.startswith("Hi, ")

    def test_mentions_pop_resubmission(self):
        # The reminder should invite the customer to send a PoP — that's the
        # loop back into the verification core.
        msg = format_reminder_message("Acme", "T", 50.0, date(2026, 6, 1), None, 0)
        assert "proof of payment" in msg
