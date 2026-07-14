"""§10 SmtpNotifier — templating + transport over an INJECTED send seam (offline: no socket; the conftest
network guard fails any real connection). Proves: push/heartbeat render the §8a subject + recipients into a
well-formed EmailMessage; the app-password NEVER leaks into repr/str; a send failure propagates (so the
runner catches it as a soft `notify` fault); and the pure `smtp_config` reader (None when unconfigured)."""

import pytest

from prospector.runner.notify import SmtpNotifier, _Secret, smtp_config


def _ctx() -> dict:
    """A minimal render context carrying a fault (so push renders the FAULT subject) — the keys
    `email_render._body` reads."""
    return {"now": "2026-07-10T00:00:00Z", "trigger": "run", "active": [], "shadow": [],
            "ceiling": {"count": 1, "ceiling": 8, "over": False, "banner": None},
            "heartbeat": {"ok": True, "ever_sent": True, "last_sent_ts": "2026-07-03T00:00:00Z",
                          "silence_days": 7, "floor_days": 7, "catch_up": False, "reason": None,
                          "last_run_ts": "2026-07-10T00:00:00Z", "last_run_date": "2026-07-10"}, "queue": [],
            "faults": [{"subsystem": "ingest.prices", "message": "XLK empty"}], "recent_faults": [],
            "changed_leads": {}, "health": {"total": 1, "active_live": 1, "active_shadow": 0,
                                            "reverted": 0, "verdicts": {}}}


def _capture():
    """An injected send seam that records the built EmailMessage instead of opening a socket."""
    sent: list = []
    return sent, sent.append


def _notifier(send, password="hunter2"):
    return SmtpNotifier(host="smtp.example.com", mail_from="a@b.com", mail_to="c@d.com",
                        password=password, send=send)


def test_push_builds_a_wellformed_message_with_the_fault_subject():
    sent, send = _capture()
    _notifier(send).push(_ctx())
    assert len(sent) == 1
    msg = sent[0]
    assert msg["From"] == "a@b.com" and msg["To"] == "c@d.com"
    assert msg["Subject"] == "[PROS] FAULT: ingest.prices"     # the ctx fault -> FAULT subject (§8a)
    assert "Scan 2026-07-10T00:00:00Z:" in msg.get_content()   # the §8a body is the message content


def test_heartbeat_uses_the_heartbeat_subject():
    sent, send = _capture()
    _notifier(send).heartbeat(_ctx())
    assert sent[0]["Subject"].startswith("[PROS] heartbeat —")
    assert "silence beyond the 7-day floor" in sent[0].get_content()


def test_subject_prefix_is_configurable():
    sent, send = _capture()
    SmtpNotifier(host="h", mail_from="a@b.com", mail_to="c@d.com", password="x",
                 subject_prefix="[PROS-TEST]", send=send).push(_ctx())
    assert sent[0]["Subject"].startswith("[PROS-TEST] FAULT:")


def test_password_never_leaks_in_repr_or_str():
    n = _notifier(lambda m: None, password="s3cr3t-pw")
    assert "s3cr3t-pw" not in repr(n) and "s3cr3t-pw" not in str(n)
    assert repr(n._secret) == "<redacted>" and str(n._secret) == "<redacted>"
    assert "s3cr3t-pw" not in repr(n._secret)
    assert isinstance(n._secret, _Secret) and n._secret.value == "s3cr3t-pw"  # readable only via .value


def test_send_failure_propagates_for_the_runner_to_catch():
    def boom(_msg):
        raise OSError("smtp connection refused")
    with pytest.raises(OSError):
        _notifier(boom).push(_ctx())


def test_smtp_config_is_none_when_unconfigured_and_a_dict_when_set():
    assert smtp_config({"email": {"to": "x@y.com"}}) is None            # no smtp_host -> email disabled
    assert smtp_config({}) is None
    sc = smtp_config({"email": {"smtp_host": "smtp.gmail.com", "to": "x@y.com",
                                "subject_prefix": "[PROS]"}})
    assert sc == {"host": "smtp.gmail.com", "port": 587, "security": "starttls",
                  "mail_from": "x@y.com", "mail_to": "x@y.com", "subject_prefix": "[PROS]"}
    # `from` overrides the self-send default.
    sc2 = smtp_config({"email": {"smtp_host": "h", "from": "bot@y.com", "to": "me@y.com"}})
    assert sc2["mail_from"] == "bot@y.com" and sc2["mail_to"] == "me@y.com"
