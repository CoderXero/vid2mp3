from audioharbor.security.urls import redact_url


def test_url_redaction_keeps_playlist_identity():
    assert redact_url('https://www.youtube.com/watch?v=x&list=y&si=secret').endswith('v=x&list=y')

