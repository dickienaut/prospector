"""Notifier seam — where the runner's outputs leave the system (spec §8a, §10).

The runner DECIDES what to send (a push is pinned to a NON-shadow `fold.state_changed` or a NEW/changed
fault — `_compute_push`, incl. the §10 nuisance-alarm suppression); the Notifier is only the transport.
Two implementations share the seam:
  - `NullNotifier` — records what WOULD be sent, sends nothing. The whole push-decision path runs offline
    (tests + an un-configured local `pros run`), no email account required.
  - `SmtpNotifier` (§10) — templates the runner's folds into the §8a heartbeat/state-change/fault emails
    (via `email_render`) and sends them over SMTP with an app-password. The app-password is a SECRET,
    handled exactly like the Tiingo token: env-only (`PROSPECTOR_SMTP_PASSWORD` from the git-ignored
    `.env`), never in config, never logged/repr'd/interpolated into a URL or exception.

CONTRACT (§10): deterministic templating only — a payload is a plain dict folded from state, never
model-generated prose (`email_render` is a pure function of the folds); and the anti-slot-machine cadence
lives in the DECISION (the runner), not here — a Notifier never manufactures a message the runner did not
ask for, and never re-decides push/suppress (that is the runner's, by the shadow-push + nuisance findings).
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Callable, Protocol

from prospector.runner import email_render


class Notifier(Protocol):
    """The transport contract the runner calls. `push` fires on a state change or a fault
    (same-day); `heartbeat` is the weekly dead-man (build-order step 4 wires the cadence)."""

    def push(self, payload: dict) -> None: ...

    def heartbeat(self, payload: dict) -> None: ...


class NullNotifier:
    """The M5-skeleton transport: record intent, send nothing. `pushes`/`heartbeats` hold what a
    real sender would have delivered — the run-log reads the counts, tests read the content. This
    keeps the push DECISION honest and testable before the sender exists (fault-on-exception still
    'emails' — it records the intended push — so the control flow is proven end to end)."""

    def __init__(self) -> None:
        self.pushes: list[dict] = []
        self.heartbeats: list[dict] = []

    def push(self, payload: dict) -> None:
        self.pushes.append(payload)

    def heartbeat(self, payload: dict) -> None:
        self.heartbeats.append(payload)


class _Secret:
    """Opaque app-password holder: str/repr are '<redacted>' so the secret can never stringify into a
    repr(), vars() dump, traceback-locals, or the append-only fossil record. Read `.value` ONLY inside the
    real send. A local copy of `ingest.prices._Secret` (same discipline) — kept here so `runner` never
    imports `ingest` just for a redaction holder."""

    __slots__ = ("_value",)

    def __init__(self, value: str | None):
        self._value = value

    def __repr__(self) -> str:
        return "<redacted>"

    __str__ = __repr__

    @property
    def value(self) -> str | None:
        return self._value


def _smtp_send(host: str, port: int, security: str, user: str, secret: _Secret,
               msg: EmailMessage) -> None:
    """The real transport: connect → (STARTTLS | SSL) → login → send. Isolated behind SmtpNotifier's
    injectable `send` seam so tests dispatch a message with NO socket (the conftest network guard fails a
    real connection). The app-password is read here and ONLY here — straight into `login`, never logged,
    never interpolated into a URL/exception (a failed login raises smtplib's own token-free error)."""
    if security == "ssl":
        with smtplib.SMTP_SSL(host, port) as s:
            s.login(user, secret.value)
            s.send_message(msg)
    else:  # "starttls" (DEFAULT — Gmail app-password on :587)
        with smtplib.SMTP(host, port) as s:
            s.starttls()
            s.login(user, secret.value)
            s.send_message(msg)


class SmtpNotifier:
    """The §10 SMTP sender: templates the runner's folds (`email_render`) into the §8a heartbeat/state-
    change/fault emails and sends them over SMTP with an app-password. `send` is an injectable transport
    seam (default `_smtp_send`) taking the built `EmailMessage`, so tests exercise render+dispatch offline.
    A send failure RAISES — `run_tick` catches it as a soft `notify` fault, so a broken sender never loses
    the run-log (the dead-man still records). The password lives in a `_Secret` holder — never repr'd/logged."""

    def __init__(self, *, host: str, port: int = 587, mail_from: str, mail_to: str,
                 password: object, subject_prefix: str = "[PROS]", security: str = "starttls",
                 send: Callable[[EmailMessage], None] | None = None) -> None:
        self.host = host
        self.port = int(port)
        self.mail_from = mail_from
        self.mail_to = mail_to
        self.subject_prefix = subject_prefix
        self.security = security
        self._secret = password if isinstance(password, _Secret) else _Secret(password)  # type: ignore[arg-type]
        self._send_fn = send  # None -> the real _smtp_send, bound at call time

    def __repr__(self) -> str:
        # Explicit repr that CANNOT carry the secret (the _Secret holder is redacted too, belt-and-braces).
        return (f"SmtpNotifier(host={self.host!r}, port={self.port!r}, from={self.mail_from!r}, "
                f"to={self.mail_to!r}, security={self.security!r})")

    def push(self, payload: dict) -> None:
        subject, body = email_render.render_push(payload, self.subject_prefix)
        self._deliver(subject, body)

    def heartbeat(self, payload: dict) -> None:
        subject, body = email_render.render_heartbeat(payload, self.subject_prefix)
        self._deliver(subject, body)

    def _deliver(self, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.mail_from
        msg["To"] = self.mail_to
        msg.set_content(body)  # plain-text/markdown-ish body (no HTML in v1)
        if self._send_fn is not None:
            self._send_fn(msg)  # injected seam (tests): receives the built message, records/dispatches it
        else:
            _smtp_send(self.host, self.port, self.security, self.mail_from, self._secret, msg)


def smtp_config(cfg: dict) -> dict | None:
    """Read the SMTP TRANSPORT config from `email.*` (host/port/security/from/to/subject_prefix). Returns
    None when unconfigured (no `email.smtp_host`) — the CLI then falls back to `NullNotifier`. PURE: it
    never reads the env — the app-password is a SECRET the CLI supplies from `PROSPECTOR_SMTP_PASSWORD`
    (env-only), never from config. `from` defaults to `to` (single-mailbox self-send, the common case)."""
    email = cfg.get("email") or {}
    host = email.get("smtp_host")
    if not host:
        return None
    return {"host": host, "port": int(email.get("smtp_port", 587)),
            "security": email.get("smtp_security", "starttls"),
            "mail_from": email.get("from") or email.get("to"),
            "mail_to": email.get("to"),
            "subject_prefix": email.get("subject_prefix", "[PROS]")}
