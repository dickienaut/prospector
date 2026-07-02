"""Config loading, hashing, and honesty (spec §5, config-honesty CONTRACT).

On every run the config is hashed; if it changed, a `config.changed` event with the diff is
appended BEFORE any sensor runs — folds stay interpretable across threshold changes. The hash
is over `envelope.canonical_json`, so it is stable under YAML key reordering and formatting.
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
    """Load YAML config and return (cfg, sha256 of its canonical JSON)."""
    with open(Path(path), encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg, hashlib.sha256(canonical_json(cfg).encode("utf-8")).hexdigest()


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
