import logging

from src.legal_content import is_legal_content_ready


def test_runtime_gate_diagnostic_logs_only_booleans(monkeypatch, caplog):
    monkeypatch.setenv("NEWSLETTER_LEGAL_READY", "true")
    monkeypatch.setenv("DIGA_TRACKER_OPERATOR_CONTACT_EMAIL", "secret@example.com")
    monkeypatch.setenv("DIGA_TRACKER_DATA_RETENTION_PERIOD", "very-secret-retention-text")

    with caplog.at_level(logging.WARNING):
        assert is_legal_content_ready() is True

    message = caplog.text
    assert "NEWSLETTER_RUNTIME_GATE" in message
    assert "switch_true=True" in message
    assert "contact_present=True" in message
    assert "retention_present=True" in message
    assert "ready=True" in message
    assert "secret@example.com" not in message
    assert "very-secret-retention-text" not in message
