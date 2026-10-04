from datetime import UTC, datetime

from audioharbor.domain.retries import retry_after


def test_retry_after_seconds_and_http_date():
    assert retry_after('12') == 12
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert retry_after('Thu, 01 Jan 2026 00:00:10 GMT', now) == 10

