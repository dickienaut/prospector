# Lenski Ledger (LTEE-Inspired Forensic Archival System)

## Status
Active (Phase 2 / Phase 3)

## Overview
The Lenski Ledger is a forensic archival system inspired by Richard Lenski's Long-Term Evolution Experiment (LTEE). It provides a complete "fossil record" of RL training: every checkpoint is a frozen "glycerol vial" containing full viable state for resurrection, every epoch logs to an append-only telemetry journal, and a SQLite registry indexes all metadata for querying without loading multi-MB weight files.

The system tracks lineages (one per currency pair), generations (each respawn creates a new generation), and checkpoints (snapshots taken at adaptive density depending on curriculum phase). An apex hall tracks the all-time best performers across lineages.

The package consists of six modules: `schemas.py` (typed containers), `archiver.py` (main orchestrator), `snapshot_policy.py` (adaptive checkpoint density), `registry.py` (SQLite metadata index), `forensics.py` (query interface), and `__init__.py` (public API).

## Theory & Design Principles

### LTEE Protocol Mapping
| LTEE Concept | Digital Equivalent |
|---|---|
| Glycerol vial | Full checkpoint (.pt) with model weights, optimizer state, RNG states |
| Transfer notebook | Append-only telemetry JSONL with per-epoch metrics |
| 500-generation archival interval | Adaptive snapshot density (cruising every 100 epochs) |
| Fitness assay | `ForensicAnalyzer.compare_checkpoints()` |
| Frozen fossil record | Sidecar JSON metadata (queryable without loading weights) |

### Adaptive Snapshot Density
Three-tier checkpoint scheduling concentrates saves where training stress is highest:

1. **Cruising altitude** (every 100 epochs): Standard heartbeat during stable phases
2. **Transition zones** (every 10 epochs): Dense saves near curriculum phase boundaries (480-620, 1400-1600) where the cosine annealer creates maximum policy stress
3. **Apex predator**: Saves whenever a new best metric is achieved during the Adult phase

### Production Fixes
Three critical fixes are baked into the archiver:

1. **CPU-staged optimizer state_dict**: `copy.deepcopy(optimizer.state_dict())` before moving tensors to CPU. Without the deepcopy, Python's pass-by-reference semantics cause live Adam momentum buffers to be moved off GPU, crashing training with `cuda:0 and cpu` device mismatch.
2. **Conditional JSONL flush**: Telemetry is only flushed to disk on checkpoint saves (not every epoch), avoiding I/O stutter during training. Worst case on crash: lose telemetry lines between saves (the checkpoint itself contains an authoritative metrics snapshot).
3. **Safe death recording**: `record_death()` flushes and closes the telemetry file handle before model objects are deleted, preventing use-after-free on the file descriptor.

## Implementation

### Schemas (`schemas.py`)

**Enums:**

| Enum | Values | Usage |
|---|---|---|
| `CurriculumPhase` | `EMBRYONIC`, `JUVENILE`, `ADULT` | Tags telemetry and checkpoints with training phase |
| `SnapshotReason` | `CRUISING`, `TRANSITION_ZONE`, `APEX`, `PLATEAU_ADVANCE`, `FINAL`, `MANUAL` | Why a checkpoint was saved |
| `DeathReason` | `DRAWDOWN_EXCEEDED`, `LOSS_DIVERGENCE`, `MANUAL_KILL` | Cause of auto-executioner kill |

**Dataclasses:**

| Class | Key Fields | Purpose |
|---|---|---|
| `EpochMetrics` | `pnl`, `trade_count`, `calmar_ratio`, `action_entropy`, `policy_std`, `jitter_filter_rate` | Per-epoch performance snapshot |
| `EnvParams` | `friction_scale`, `latency_ticks`, `direction_reward_weight`, `entropy_coefficient` | Curriculum state at time of snapshot |
| `CheckpointMeta` | `checkpoint_id`, `lineage`, `generation`, `epoch`, `phase`, `reason`, `sha256`, `file_path`, `is_apex`, `metrics`, `env_params` | Sidecar metadata for a checkpoint file |

### Archiver (`archiver.py`)

**`LTEEArchiver.__init__(archive_root, lineage, generation, dna_config, ...)`**

Creates the directory structure `{archive_root}/{lineage}/gen_{generation:03d}/{checkpoints,sidecar}/`, initializes the SQLite registry, registers the lineage and generation, freezes the DNA config to JSON, and opens the telemetry JSONL file for append.

**`log_epoch(epoch, metrics, env_params, lr, loss_policy, loss_value, loss_entropy, grad_norm)`**

Appends a JSONL record with all metrics, curriculum phase, and training diagnostics. Returns `(should_save: bool, reason: SnapshotReason | None, phase: CurriculumPhase)` based on the adaptive snapshot policy.

**`save_checkpoint(epoch, phase, reason, metrics, env_params, perception_engine, ppo_agent, optimizer, scaler=None)`**

Saves a full-resurrection checkpoint containing:
- Model weights (perception engine + PPO agent)
- CPU-staged optimizer state (deepcopy to prevent VRAM spike and live buffer mutation)
- All four RNG states (torch CPU, torch CUDA, numpy, Python random)
- Curriculum position, environment params, provenance metadata

Uses atomic save (write to `.pt.tmp` then rename) for crash safety. Computes SHA-256 integrity hash. Writes sidecar JSON metadata and registers in SQLite. For apex checkpoints, updates the symlink, generation metadata, registry, and global apex hall.

**`record_death(epoch, reason)`** / **`record_graduation()`**

Close out the generation's telemetry, update the registry, and write final metadata. `record_death()` MUST be called before deleting model objects.

**`LTEEArchiver.resurrect(checkpoint_path, perception_engine, ppo_agent, optimizer, scaler, device)` (static)**

Restores model weights, optimizer state, and all four RNG states for exact training reproduction from any historical checkpoint.

### Snapshot Policy (`snapshot_policy.py`)

**`AdaptiveSnapshotPolicy(phase_1_end, phase_2_end, total_epochs, apex_metric)`**

| Trigger | Condition | Reason |
|---|---|---|
| Final epoch | `epoch >= total_epochs` | `FINAL` |
| Apex predator | New high-water mark on `apex_metric` during Adult phase | `APEX` |
| Transition zone | Every 10 epochs within `(480, 620)` or `(1400, 1600)` | `TRANSITION_ZONE` |
| Cruising | Every 100 epochs (outside transition zones) | `CRUISING` |

### Registry (`registry.py`)

**`FossilRegistry(db_path)`** — SQLite with WAL journal mode for concurrent read/write.

**Tables:**

| Table | Primary Key | Purpose |
|---|---|---|
| `lineages` | `lineage_id` (TEXT) | One row per currency pair |
| `generations` | `(lineage_id, generation)` UNIQUE | Tracks spawns, deaths, graduations, apex stats |
| `checkpoints` | `checkpoint_id` (TEXT UNIQUE) | Full metrics + file metadata per checkpoint |
| `apex_history` | auto-increment | Tracks apex succession with `superseded_by` chain |

**Indexes:** `idx_ckpt_lineage_gen` (lineage, generation, epoch), `idx_ckpt_apex` (partial on `is_apex=TRUE`), `idx_ckpt_phase` (curriculum phase, epoch).

### Forensics (`forensics.py`)

**`ForensicAnalyzer(archive_root)`** — Read-only query interface (requires pandas for most methods).

| Method | Returns |
|---|---|
| `compare_checkpoints(id_a, id_b)` | Head-to-head dict with metric deltas |
| `lineage_trajectory(lineage)` | DataFrame of all checkpoints for a lineage across generations |
| `cross_lineage_at_epoch(epoch)` | DataFrame comparing all lineages at a specific epoch |
| `generational_drift(lineage)` | DataFrame of apex stats across respawn generations |
| `extinction_report()` | DataFrame of all auto-executioner kills |
| `global_apex_ranking(top_n)` | DataFrame ranking best checkpoints by calmar_ratio |
| `load_telemetry(lineage, generation)` | DataFrame from epoch-by-epoch telemetry JSONL |

## Input / Output

### Directory Structure
```
ltee_archive/
  archive_manifest.json          Global manifest (schema version, lineages)
  apex_hall.json                 Best-ever per lineage + global best
  registry.sqlite                SQLite metadata index (WAL mode)
  {lineage}/
    gen_{NNN}/
      gen_meta.json              Generation status, apex stats, DNA hash
      dna_{lineage}.json         Frozen DNA config
      telemetry.jsonl            Per-epoch append-only metrics
      checkpoints/
        ckpt_e{NNNN}.pt         Full resurrection checkpoint
        apex.pt -> ckpt_eXXXX.pt  Symlink to best checkpoint
      sidecar/
        ckpt_e{NNNN}.json       Queryable metadata without loading weights
```

### Checkpoint Contents (`.pt` file)
| Key | Type | Description |
|---|---|---|
| `perception_state_dict` | dict | Perception engine weights |
| `ppo_agent_state_dict` | dict | PPO agent weights |
| `optimizer_state_dict` | dict | CPU-staged Adam optimizer state |
| `scaler_state_dict` | dict/None | AMP GradScaler state |
| `rng_states` | dict | torch CPU, torch CUDA, numpy, Python RNG states |
| `epoch`, `lineage`, `generation` | int/str | Provenance |
| `curriculum_phase`, `snapshot_reason` | str | Training context |
| `metrics`, `env_params` | dict | Performance and curriculum snapshot |

## Integration Points

### Dependencies
- `torch`, `numpy`, `random` — for state capture and serialization
- `sqlite3` — metadata registry
- `pandas` (optional) — forensic analysis queries

### Dependents
- `training/train_ppo.py` — imports `LTEEArchiver`, `EpochMetrics`, `EnvParams`; calls `log_epoch()`, `save_checkpoint()`, `record_death()`, `record_graduation()` per generation
- `training/stepped_curriculum.py` — triggers `PLATEAU_ADVANCE` saves via the archiver

## Configuration

### Key Constants
| Parameter | Default | Description |
|---|---|---|
| `cruising_interval` | 100 | Epochs between standard heartbeat saves |
| `transition_interval` | 10 | Epochs between saves in transition zones |
| `transition_margin` | 20 | Epochs before/after phase boundary for transition zones |
| `apex_metric` | `calmar_ratio` | Metric tracked for apex predator saves |
