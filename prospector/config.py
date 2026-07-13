"""Config loading, hashing, and honesty (spec §5, config-honesty CONTRACT).

On every run the config is hashed; if it changed, a `config.changed` event with the diff is
appended BEFORE any sensor runs — folds stay interpretable across threshold changes. The hash
is over `envelope.canonical_json`, so it is stable under YAML key reordering and formatting.

An optional untracked `config/prospector.local.yaml` overlay carries MACHINE-LOCAL values —
store.root, backup.targets, the EDGAR contact — that must never enter the shared repo (the config
analog of the git-ignored `.env` secrets). It is deep-merged OVER the tracked config in `load_config`,
and the hash is over the EFFECTIVE MERGED config, so `config.changed` fossils exactly the config the
run used — config honesty holds across the overlay. (Non-secret machine config is *recorded* here;
true secrets stay in `.env` and never touch config.) See
docs/decisions/2026-07-12-local-config-overlay.md.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

import yaml

from prospector.store.envelope import SYSTEM_LEAD, canonical_json
from prospector.store.registry import Registry

META_HASH_KEY = "last_config_hash"
META_JSON_KEY = "last_config_json"


def load_config(path) -> tuple[dict, str]:
    """Load YAML config — deep-merged with an optional untracked local overlay — and return
    (cfg, sha256 of its canonical JSON over the EFFECTIVE MERGED config).

    A sibling `prospector.local.yaml` (untracked, gitignored — machine-local values, see the module
    docstring) is deep-merged over the tracked config when present. The overlay is resolved as a
    SIBLING of the *passed* path — never a fixed cwd-relative path — so loading a throwaway/tmp config
    (dev tests, backtests) never picks up an unrelated repo overlay. Absent overlay → the base config
    unchanged. The hash is computed AFTER the merge, so it (and `config.changed`) cover the config the
    run actually used."""
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    local = path.with_name("prospector.local.yaml")
    if local.is_file():
        with open(local, encoding="utf-8") as f:
            overlay = yaml.safe_load(f) or {}
        if not isinstance(overlay, dict):
            raise ValueError(
                f"{local} must be a YAML mapping (got {type(overlay).__name__}) — the local overlay "
                "carries machine-local config keys like store.root / backup.targets, so its root is a map.")
        cfg = _deep_merge(cfg, overlay)
    return cfg, hashlib.sha256(canonical_json(cfg).encode("utf-8")).hexdigest()


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge `overlay` onto `base` (overlay wins); returns a new top-level dict without
    mutating either input. Nested dicts merge key-by-key; every other value — scalars AND lists —
    REPLACES wholesale, so an overlay `backup.targets: [...]` overrides the tracked list rather than
    appending. (Nested overlay containers are shared into the result, not deep-copied — safe here because
    the overlay is a transient re-parsed from disk on every `load_config` call and then discarded.)"""
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def flatten(cfg, prefix: str = "") -> dict:
    """Flatten nested config to {dot.path: scalar} for diffs; list items key by index.
    Empty containers stay as leaves so their presence survives into a diff."""
    if isinstance(cfg, dict):
        items = [(str(k), v) for k, v in cfg.items()]
    elif isinstance(cfg, list):
        items = [(str(i), v) for i, v in enumerate(cfg)]
    else:
        return {prefix: cfg}
    out: dict = {}
    for key, value in items:
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, (dict, list)) and value:
            out.update(flatten(value, path))
        else:
            out[path] = value
    return out


def config_diff(old: dict, new: dict) -> dict:
    """Diff two configs over their flattened dot-paths."""
    flat_old, flat_new = flatten(old), flatten(new)
    return {
        "changed": {k: {"old": flat_old[k], "new": flat_new[k]}
                    for k in sorted(flat_old.keys() & flat_new.keys())
                    if flat_old[k] != flat_new[k]},
        "added": {k: flat_new[k] for k in sorted(flat_new.keys() - flat_old.keys())},
        "removed": {k: flat_old[k] for k in sorted(flat_old.keys() - flat_new.keys())},
    }


def check_config_honesty(cfg: dict, cfg_hash: str, registry: Registry,
                         append: Callable[[dict], object], now: str) -> bool:
    """Emit `config.changed` (with the diff) if the config hash moved since the last run.

    `append` is any callable taking the raw event dict — production wires EventStore.append.
    The CONTRACT is ordering: the runner calls this first, and the event is appended BEFORE
    the meta keys are updated, so a crash in between re-emits on the next run rather than
    silently swallowing the change. First ever run records meta and emits nothing — nothing
    changed. Returns True iff an event was emitted.
    """
    last_hash = registry.get_meta(META_HASH_KEY)
    if last_hash is None:
        registry.set_meta(META_JSON_KEY, canonical_json(cfg))
        registry.set_meta(META_HASH_KEY, cfg_hash)
        return False
    if last_hash == cfg_hash:
        return False
    old_cfg = json.loads(registry.get_meta(META_JSON_KEY) or "{}")
    append({"ts": now, "lead": SYSTEM_LEAD, "type": "config.changed",
            "payload": {"diff": config_diff(old_cfg, cfg),
                        "old_hash": last_hash, "new_hash": cfg_hash},
            "schema": 1})
    # JSON before hash: a crash between the two re-emits (with an empty diff) on the next
    # run instead of leaving a stale diff base under a matching hash.
    registry.set_meta(META_JSON_KEY, canonical_json(cfg))
    registry.set_meta(META_HASH_KEY, cfg_hash)
    return True
