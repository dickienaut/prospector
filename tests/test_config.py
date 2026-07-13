"""Config loading, hashing, and honesty (spec §5, config-honesty CONTRACT): the hash is
content-addressed (stable under YAML key order), and a change emits `config.changed` with the
diff BEFORE the stored baseline is updated."""

import json

import pytest

from prospector.config import (META_HASH_KEY, META_JSON_KEY, check_config_honesty, config_diff,
                               flatten, load_config)
from prospector.store.envelope import validate

NOW = "2026-07-02T00:00:00Z"


# -- load_config --------------------------------------------------------------

def test_hash_stable_under_yaml_key_reordering(tmp_path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text("xcorr:\n  z_in: 2.5\n  z_out: 1.0\nwindows:\n  corr_days: 63\n",
                 encoding="utf-8")
    b.write_text("windows:\n  corr_days: 63\nxcorr:\n  z_out: 1.0\n  z_in: 2.5\n",
                 encoding="utf-8")
    cfg_a, hash_a = load_config(a)
    cfg_b, hash_b = load_config(b)
    assert cfg_a == cfg_b
    assert hash_a == hash_b


def test_hash_moves_when_a_value_moves(tmp_path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text("xcorr:\n  z_in: 2.5\n", encoding="utf-8")
    b.write_text("xcorr:\n  z_in: 3.0\n", encoding="utf-8")
    assert load_config(a)[1] != load_config(b)[1]


# -- local overlay (untracked machine-local config) ---------------------------

def test_absent_local_overlay_is_a_noop(tmp_path):
    # No sibling prospector.local.yaml -> base config unchanged. This is the dev/tmp/backtest case: a
    # throwaway config must never inherit an unrelated repo overlay (the sibling-resolution guarantee).
    base = tmp_path / "prospector.yaml"
    base.write_text("store:\n  root: ./store\nxcorr:\n  z_in: 2.5\n", encoding="utf-8")
    cfg, h = load_config(base)
    assert cfg == {"store": {"root": "./store"}, "xcorr": {"z_in": 2.5}}
    assert (cfg, h) == load_config(base)


def test_local_overlay_deep_merges_over_base_and_moves_hash(tmp_path):
    base = tmp_path / "prospector.yaml"
    base.write_text("store:\n  root: ./store\nxcorr:\n  z_in: 2.5\n", encoding="utf-8")
    _, base_hash = load_config(base)
    (tmp_path / "prospector.local.yaml").write_text(
        "store:\n  root: /abs/store\nbackup:\n  targets: [/Volumes/A, /Volumes/B]\n", encoding="utf-8")
    cfg, merged_hash = load_config(base)
    assert cfg["store"]["root"] == "/abs/store"                 # overlay wins
    assert cfg["backup"]["targets"] == ["/Volumes/A", "/Volumes/B"]
    assert cfg["xcorr"]["z_in"] == 2.5                          # base preserved
    assert merged_hash != base_hash                             # hash is over the MERGED config


def test_local_overlay_is_resolved_as_sibling_of_the_passed_path(tmp_path):
    # An overlay next to config A must NOT bleed into loading config B in another directory.
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a = tmp_path / "a" / "prospector.yaml"
    a.write_text("store:\n  root: ./store\n", encoding="utf-8")
    b = tmp_path / "b" / "prospector.yaml"
    b.write_text("store:\n  root: ./store\n", encoding="utf-8")
    (tmp_path / "a" / "prospector.local.yaml").write_text("store:\n  root: /only/for/a\n", encoding="utf-8")
    assert load_config(a)[0]["store"]["root"] == "/only/for/a"
    assert load_config(b)[0]["store"]["root"] == "./store"      # b unaffected by a's overlay


def test_overlay_replaces_lists_wholesale_not_append(tmp_path):
    base = tmp_path / "prospector.yaml"
    base.write_text("backup:\n  targets: [/old/x, /old/y]\n  marker: .m\n", encoding="utf-8")
    (tmp_path / "prospector.local.yaml").write_text("backup:\n  targets: [/new/z]\n", encoding="utf-8")
    cfg, _ = load_config(base)
    assert cfg["backup"]["targets"] == ["/new/z"]               # replaced, not [/old/x, /old/y, /new/z]
    assert cfg["backup"]["marker"] == ".m"                      # sibling key preserved (deep merge)


def test_overlay_migration_preserves_hash_when_effective_config_is_identical(tmp_path):
    # The migration invariant: moving a value from the tracked file INTO the overlay (with the tracked
    # file reset to the default) leaves the EFFECTIVE config — and so the hash — unchanged, so the
    # first prod run after migration emits NO spurious config.changed.
    combined = tmp_path / "combined" / "prospector.yaml"
    combined.parent.mkdir()
    combined.write_text("store:\n  root: /abs/store\nxcorr:\n  z_in: 2.5\n", encoding="utf-8")
    _, hash_before = load_config(combined)                      # value in the tracked file

    split = tmp_path / "split" / "prospector.yaml"
    split.parent.mkdir()
    split.write_text("store:\n  root: ./store\nxcorr:\n  z_in: 2.5\n", encoding="utf-8")   # default
    (split.parent / "prospector.local.yaml").write_text("store:\n  root: /abs/store\n", encoding="utf-8")
    _, hash_after = load_config(split)                          # same value, now via the overlay
    assert hash_after == hash_before


def test_non_dict_local_overlay_fails_loud(tmp_path):
    # A malformed overlay (non-mapping root) must fail with a clear, file-named error — before any run —
    # never a cryptic AttributeError deep in the merge.
    base = tmp_path / "prospector.yaml"
    base.write_text("store:\n  root: ./store\n", encoding="utf-8")
    (tmp_path / "prospector.local.yaml").write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        load_config(base)


# -- flatten / config_diff ----------------------------------------------------

def test_flatten_dot_paths_and_list_indices():
    cfg = {"xcorr": {"z_in": 2.5}, "universe": {"sectors": ["XLK", "XLU"]}, "s3": {"bucket": None}}
    assert flatten(cfg) == {"xcorr.z_in": 2.5, "universe.sectors.0": "XLK",
                            "universe.sectors.1": "XLU", "s3.bucket": None}


def test_config_diff_changed_added_removed():
    old = {"xcorr": {"z_in": 2.5, "z_out": 1.0}, "identity": {"retry_days": 10}}
    new = {"xcorr": {"z_in": 3.0, "z_out": 1.0}, "oracle": {"active_lead_ceiling": 8}}
    diff = config_diff(old, new)
    assert diff == {
        "changed": {"xcorr.z_in": {"old": 2.5, "new": 3.0}},
        "added": {"oracle.active_lead_ceiling": 8},
        "removed": {"identity.retry_days": 10},
    }


def test_config_diff_identical_is_empty():
    cfg = {"xcorr": {"z_in": 2.5}, "universe": {"sectors": ["XLK", "XLU"]}}
    assert config_diff(cfg, cfg) == {"changed": {}, "added": {}, "removed": {}}


# -- check_config_honesty -----------------------------------------------------

def test_first_run_records_meta_and_emits_nothing(registry):
    calls = []
    changed = check_config_honesty({"xcorr": {"z_in": 2.5}}, "hash_old", registry,
                                   calls.append, NOW)
    assert changed is False
    assert calls == []
    assert registry.get_meta(META_HASH_KEY) == "hash_old"
    assert json.loads(registry.get_meta(META_JSON_KEY)) == {"xcorr": {"z_in": 2.5}}


def test_change_emits_one_event_before_meta_update(registry):
    check_config_honesty({"xcorr": {"z_in": 2.5}}, "hash_old", registry, lambda e: None, NOW)

    seen = []

    def spy(event):
        # Reading meta inside the append proves the event lands BEFORE meta is updated
        # (CONTRACT: config.changed precedes any sensor run; a crash after append re-emits).
        seen.append((event, registry.get_meta(META_HASH_KEY)))

    changed = check_config_honesty({"xcorr": {"z_in": 3.0}}, "hash_new", registry, spy, NOW)
    assert changed is True
    assert len(seen) == 1

    event, hash_at_append_time = seen[0]
    assert hash_at_append_time == "hash_old"
    validate(event)  # the raw dict is a legal envelope
    assert event["ts"] == NOW
    assert event["lead"] == "_system"
    assert event["type"] == "config.changed"
    assert event["payload"]["old_hash"] == "hash_old"
    assert event["payload"]["new_hash"] == "hash_new"
    assert event["payload"]["diff"]["changed"] == {"xcorr.z_in": {"old": 2.5, "new": 3.0}}

    assert registry.get_meta(META_HASH_KEY) == "hash_new"
    assert json.loads(registry.get_meta(META_JSON_KEY)) == {"xcorr": {"z_in": 3.0}}


def test_unchanged_rerun_after_change_emits_no_second_event(registry):
    check_config_honesty({"xcorr": {"z_in": 2.5}}, "hash_old", registry, lambda e: None, NOW)
    check_config_honesty({"xcorr": {"z_in": 3.0}}, "hash_new", registry, lambda e: None, NOW)

    calls = []
    changed = check_config_honesty({"xcorr": {"z_in": 3.0}}, "hash_new", registry,
                                   calls.append, "2026-07-03T00:00:00Z")
    assert changed is False
    assert calls == []
    assert registry.get_meta(META_HASH_KEY) == "hash_new"
