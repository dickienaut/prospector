"""The frozen five-field envelope (spec §5, CONTRACT): exactly five keys, UTC-only ts,
path-safe lead, open `type` vocabulary, JSON-object payload, positive-int schema."""

import json
import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from prospector.store.envelope import (
    FIELDS,
    SYSTEM_LEAD,
    Envelope,
    EnvelopeError,
    canonical_json,
    validate,
)


def make_event(**over):
    e = {"ts": "2026-07-14T13:00:00Z", "lead": "lead_abc123", "type": "xcorr.tick",
         "payload": {"z": 3.2}, "schema": 1}
    e.update(over)
    return e


# -- five fields exactly -----------------------------------------------------

def test_valid_event_round_trips():
    raw = make_event()
    env = validate(raw)
    assert isinstance(env, Envelope)
    assert env.to_dict() == raw


def test_extra_key_rejected():
    raw = make_event()
    raw["note"] = "sixth field"
    with pytest.raises(EnvelopeError):
        validate(raw)


@pytest.mark.parametrize("field", FIELDS)
def test_missing_key_rejected(field):
    raw = make_event()
    del raw[field]
    with pytest.raises(EnvelopeError):
        validate(raw)


def test_non_dict_event_rejected():
    with pytest.raises(EnvelopeError):
        validate(["ts", "lead", "type", "payload", "schema"])


# -- ts: ISO-8601, explicitly UTC ---------------------------------------------

@pytest.mark.parametrize("ts", [
    "not-a-time",
    "2026-13-45T99:00:00Z",
    "2026-07-14T13:00:00",        # naive
    "2026-07-14T13:00:00+05:00",  # non-UTC offset
    1720962000,                   # not a string
])
def test_bad_ts_rejected(ts):
    with pytest.raises(EnvelopeError):
        validate(make_event(ts=ts))


def test_explicit_utc_offset_accepted():
    env = validate(make_event(ts="2026-07-14T13:00:00+00:00"))
    assert env.ts == "2026-07-14T13:00:00+00:00"


# -- payload: JSON object, strict numbers -------------------------------------

@pytest.mark.parametrize("payload", [[1, 2], "text", 3.2, None, True])
def test_non_dict_payload_rejected(payload):
    with pytest.raises(EnvelopeError):
        validate(make_event(payload=payload))


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_number_in_payload_rejected(bad):
    # canonical_json uses allow_nan=False: NaN/Infinity are not JSON.
    with pytest.raises(EnvelopeError):
        validate(make_event(payload={"z": bad}))


def test_nan_nested_in_payload_rejected():
    with pytest.raises(EnvelopeError):
        validate(make_event(payload={"a": {"b": [1, math.nan]}}))


_json_scalars = (st.none() | st.booleans() | st.integers()
                 | st.floats(allow_nan=False, allow_infinity=False) | st.text())
_json_values = st.recursive(
    _json_scalars,
    lambda children: (st.lists(children, max_size=3)
                      | st.dictionaries(st.text(max_size=8), children, max_size=3)),
    max_leaves=10)
_payloads = st.dictionaries(st.text(max_size=8), _json_values, max_size=4)


@given(payload=_payloads)
def test_any_json_object_payload_accepted_and_round_trips(payload):
    env = validate(make_event(payload=payload))
    assert json.loads(canonical_json(env.payload)) == payload


# -- type: open vocabulary (CONTRACT — never an enum) --------------------------

@pytest.mark.parametrize("type_", [
    "v2.some.future_type",
    "llm.thesis_drafted",
    "UPPER-case With spaces",
    "☃.unicode",
])
def test_unforeseen_type_strings_accepted(type_):
    assert validate(make_event(type=type_)).type == type_


@given(type_=st.text(min_size=1).filter(lambda s: s.strip()))
def test_open_type_vocabulary_property(type_):
    # Any non-blank string is a valid type: a new event type needs no code change,
    # no migration — the system's whole premise (spec §5).
    assert validate(make_event(type=type_)).type == type_


@pytest.mark.parametrize("type_", ["", "   ", None, 7])
def test_blank_or_non_string_type_rejected(type_):
    with pytest.raises(EnvelopeError):
        validate(make_event(type=type_))


# -- lead: path-safe or the reserved '_system' ---------------------------------

@pytest.mark.parametrize("lead", ["a/b", "", "../up", "a b", None])
def test_non_path_safe_lead_rejected(lead):
    with pytest.raises(EnvelopeError):
        validate(make_event(lead=lead))


def test_system_lead_accepted():
    assert validate(make_event(lead=SYSTEM_LEAD)).lead == "_system"


# -- schema: positive int, bools excluded ---------------------------------------

@pytest.mark.parametrize("schema", [0, True, False, -1, "1", 1.0, None])
def test_bad_schema_rejected(schema):
    with pytest.raises(EnvelopeError):
        validate(make_event(schema=schema))


# -- S3: the lead regex rejects a trailing newline (\Z, not $) --------------------------------

def test_lead_with_a_trailing_newline_rejected():
    # `$` would admit "lead_abc\n" as a valid lead, letting a newline into a path component under
    # events/ ; `\Z` anchors the true end of the string. The valid form still passes.
    validate(make_event(lead="lead_abc"))  # no raise
    with pytest.raises(EnvelopeError):
        validate(make_event(lead="lead_abc\n"))
