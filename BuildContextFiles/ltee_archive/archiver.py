"""LTEEArchiver — the frozen fossil record for RL training lineages.

Mirrors Lenski's LTEE archival protocol:
- Every checkpoint is a 'glycerol vial' containing full viable state
- Every epoch logs to the 'transfer notebook' (telemetry.jsonl)
- The apex_hall tracks best-ever across all generations
- Lineage genealogy records births, deaths, and respawns

Production fixes integrated:
1. CPU-staged optimizer state_dict (prevents VRAM spike during saves)
2. Conditional JSONL flush (only on checkpoint saves, avoids I/O stutter)
3. record_death() safe to call before model deletion
"""

import copy
import torch
import json
import hashlib
import random
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict

from .schemas import (
    CurriculumPhase, SnapshotReason, EpochMetrics, EnvParams, CheckpointMeta
)
from .snapshot_policy import AdaptiveSnapshotPolicy
from .registry import FossilRegistry


# --- Instrument name lookup ---
INSTRUMENT_NAMES = {
    "6E": "Euro FX Futures", "6J": "Japanese Yen Futures",
    "6B": "British Pound Futures", "6A": "Australian Dollar Futures",
    "6C": "Canadian Dollar Futures", "6S": "Swiss Franc Futures",
    "6N": "New Zealand Dollar Futures", "6M": "Mexican Peso Futures",
}


def _cpu_optimizer_state_dict(optimizer):
    """FIX #1: Stage optimizer state to CPU to prevent VRAM spike during serialization.

    Adam maintains exp_avg and exp_avg_sq buffers for every parameter. With mixed
    BF16/FP32 precision, calling state_dict() can cause a temporary VRAM spike as
    PyTorch serializes momentum buffers. This function moves them to system RAM first.
    """
    sd = copy.deepcopy(optimizer.state_dict())
    for param_id, state in sd.get("state", {}).items():
        for key, val in state.items():
            if isinstance(val, torch.Tensor):
                state[key] = val.cpu()
    return sd


class LTEEArchiver:

    def __init__(self, archive_root, lineage, generation, dna_config,
                 spawn_reason="initial", parent_gen=None,
                 phase_1_end=500, phase_2_end=1500, total_epochs=3000,
                 apex_metric="calmar_ratio"):

        self.root = Path(archive_root)
        self.lineage = lineage
        self.generation = generation
        self.gen_dir = self.root / lineage / f"gen_{generation:03d}"
        self.ckpt_dir = self.gen_dir / "checkpoints"
        self.sidecar_dir = self.gen_dir / "sidecar"

        # Create directory structure
        self.ckpt_dir.mkdir(parents=True, exist_ok=True)
        self.sidecar_dir.mkdir(parents=True, exist_ok=True)

        # Initialize snapshot policy (curriculum-aware density)
        self.policy = AdaptiveSnapshotPolicy(
            phase_1_end=phase_1_end, phase_2_end=phase_2_end,
            total_epochs=total_epochs, apex_metric=apex_metric,
        )

        # Initialize SQLite registry
        self.registry = FossilRegistry(str(self.root / "registry.sqlite"))

        # Ensure lineage exists in registry
        now_iso = datetime.now(timezone.utc).isoformat()
        self.registry.ensure_lineage(
            lineage, INSTRUMENT_NAMES.get(lineage, lineage), now_iso
        )

        # Register this generation
        dna_hash = hashlib.sha256(
            json.dumps(dna_config, sort_keys=True).encode()
        ).hexdigest()
        self.registry.register_generation(
            lineage, generation, spawn_reason, parent_gen, dna_hash, now_iso
        )

        # Freeze DNA config (archive even if unchanged from previous generation)
        dna_path = self.gen_dir / f"dna_{lineage}.json"
        with open(dna_path, "w") as f:
            json.dump(dna_config, f, indent=2)

        # Write generation metadata
        self._gen_meta = {
            "lineage": lineage, "generation": generation,
            "spawn_reason": spawn_reason, "parent_generation": parent_gen,
            "started": now_iso, "ended": None, "status": "training",
            "dna_hash": dna_hash, "total_epochs_completed": 0,
            "apex_epoch": None, "apex_calmar": None, "apex_pnl": None,
            "graduated": False,
        }
        self._save_gen_meta()

        # Open telemetry file (append-only JSONL)
        self._telemetry_path = self.gen_dir / "telemetry.jsonl"
        self._telemetry_fh = open(self._telemetry_path, "a")

        # Initialize archive manifest if it doesn't exist
        manifest_path = self.root / "archive_manifest.json"
        if not manifest_path.exists():
            with open(manifest_path, "w") as f:
                json.dump({
                    "schema_version": 1,
                    "created": now_iso,
                    "lineages": list(INSTRUMENT_NAMES.keys()),
                }, f, indent=2)

    def log_epoch(self, epoch, metrics: EpochMetrics, env_params: EnvParams,
                  lr, loss_policy, loss_value, loss_entropy, grad_norm):
        """Log per-epoch telemetry and determine if a checkpoint should be saved.

        Returns: (should_save: bool, reason: SnapshotReason | None, phase: CurriculumPhase)
        """
        phase = self.policy.get_phase(epoch)
        should_save, reason = self.policy.should_save(epoch, metrics)

        record = {
            "epoch": epoch,
            "phase": phase.value,
            "wall_time": datetime.now(timezone.utc).isoformat(),
            **asdict(metrics),
            **asdict(env_params),
            "lr": lr,
            "loss_policy": round(loss_policy, 6) if loss_policy else None,
            "loss_value": round(loss_value, 6) if loss_value else None,
            "loss_entropy": round(loss_entropy, 6) if loss_entropy else None,
            "grad_norm": round(grad_norm, 4) if grad_norm else None,
            "checkpoint_saved": should_save,
            "snapshot_reason": reason.value if reason else None,
        }

        # Append to JSONL
        self._telemetry_fh.write(json.dumps(record) + "\n")

        # FIX #2: Only flush when we're saving a checkpoint anyway (avoids I/O stutter).
        # Worst case on crash: lose last few telemetry lines between saves.
        # The checkpoint itself contains the metrics snapshot as authoritative record.
        if should_save:
            self._telemetry_fh.flush()

        # Update generation metadata
        self._gen_meta["total_epochs_completed"] = epoch

        return should_save, reason, phase

    def save_checkpoint(self, epoch, phase: CurriculumPhase, reason: SnapshotReason,
                        metrics: EpochMetrics, env_params: EnvParams,
                        perception_engine, ppo_agent, optimizer, scaler=None):
        """Save a full-resurrection checkpoint (the 'glycerol vial').

        Contains: model weights, optimizer state (CPU-staged), RNG states,
        curriculum position, environment params, and provenance metadata.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        checkpoint = {
            # === Full resurrection state ===
            "perception_state_dict": perception_engine.state_dict(),
            "ppo_agent_state_dict": ppo_agent.state_dict(),
            # FIX #1: CPU-staged optimizer state to prevent VRAM spike
            "optimizer_state_dict": _cpu_optimizer_state_dict(optimizer),
            "scaler_state_dict": scaler.state_dict() if scaler else None,

            # === RNG states (exact reproduction) ===
            "rng_states": {
                "torch_cpu": torch.get_rng_state(),
                "torch_cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
                "numpy": np.random.get_state(),
                "python": random.getstate(),
            },

            # === Provenance ===
            "lineage": self.lineage,
            "generation": self.generation,
            "epoch": epoch,
            "curriculum_phase": phase.value,
            "snapshot_reason": reason.value,
            "wall_time": now_iso,
            "metrics": asdict(metrics),
            "env_params": asdict(env_params),
            "pytorch_version": torch.__version__,
        }

        # Atomic save: write to .tmp then rename (crash-safe)
        filename = f"ckpt_e{epoch:04d}.pt"
        filepath = self.ckpt_dir / filename
        tmp_path = filepath.with_suffix(".pt.tmp")
        torch.save(checkpoint, str(tmp_path))
        tmp_path.rename(filepath)

        # Compute integrity hash
        sha256 = hashlib.sha256(filepath.read_bytes()).hexdigest()
        file_size = filepath.stat().st_size

        checkpoint_id = f"{self.lineage}-g{self.generation:03d}-e{epoch:04d}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

        # Write sidecar metadata (queryable without loading multi-MB .pt file)
        meta = CheckpointMeta(
            checkpoint_id=checkpoint_id,
            lineage=self.lineage,
            generation=self.generation,
            epoch=epoch,
            phase=phase.value,
            reason=reason.value,
            wall_time=now_iso,
            sha256=sha256,
            file_size=file_size,
            file_path=str(filepath.relative_to(self.root)),
            is_apex=(reason == SnapshotReason.APEX),
            metrics=asdict(metrics),
            env_params=asdict(env_params),
        )

        sidecar_path = self.sidecar_dir / f"ckpt_e{epoch:04d}.json"
        with open(sidecar_path, "w") as f:
            json.dump(asdict(meta), f, indent=2)

        # Register in SQLite
        self.registry.register_checkpoint(meta)

        # Handle apex predator tracking
        if reason == SnapshotReason.APEX:
            # Update symlink to best-ever this generation
            apex_link = self.ckpt_dir / "apex.pt"
            if apex_link.is_symlink() or apex_link.exists():
                apex_link.unlink()
            apex_link.symlink_to(filename)

            # Update generation metadata
            self._gen_meta["apex_epoch"] = epoch
            self._gen_meta["apex_calmar"] = metrics.calmar_ratio
            self._gen_meta["apex_pnl"] = metrics.pnl
            self._save_gen_meta()

            # Update registry
            self.registry.update_generation_apex(
                self.lineage, self.generation, epoch,
                metrics.calmar_ratio, metrics.pnl
            )

            # Update global apex hall
            self._update_apex_hall(meta)

            print(f"  [{self.lineage}] New apex predator at epoch {epoch} | "
                  f"Calmar: {metrics.calmar_ratio:.3f} | PnL: ${metrics.pnl:+.0f}")

        return checkpoint_id

    def record_death(self, epoch, reason):
        """FIX #3: Record an Auto-Executioner kill. MUST be called BEFORE deleting model objects.

        This closes out the generation's telemetry, updates the registry, and
        writes final metadata. Safe to call even if telemetry file handle is still open.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # Flush any remaining telemetry
        self._telemetry_fh.flush()
        self._telemetry_fh.close()

        # Update generation metadata
        self._gen_meta["ended"] = now_iso
        self._gen_meta["status"] = f"killed:{reason}"
        self._save_gen_meta()

        # Update registry
        self.registry.record_death(self.lineage, self.generation, epoch, reason, now_iso)

        print(f"  [{self.lineage}] Generation {self.generation} died at epoch {epoch}: {reason}")

    def record_graduation(self):
        """Record successful graduation (survived all epochs)."""
        now_iso = datetime.now(timezone.utc).isoformat()

        self._telemetry_fh.flush()
        self._telemetry_fh.close()

        self._gen_meta["ended"] = now_iso
        self._gen_meta["status"] = "graduated"
        self._gen_meta["graduated"] = True
        self._save_gen_meta()

        self.registry.record_graduation(self.lineage, self.generation, now_iso)

        print(f"  [{self.lineage}] Generation {self.generation} GRADUATED!")

    def upload_lineage_to_s3(self, bucket="prophit-brains-archive"):
        """Upload generation metadata + apex checkpoint to S3 after graduation.

        Fire-and-forget: network failures are caught and logged, never crash training.
        """
        try:
            from .s3_uploader import S3ArchiveUploader
            uploader = S3ArchiveUploader(bucket)

            # Upload all metadata (gen_meta, dna, telemetry, exploit_log, sidecars)
            uploader.upload_generation_metadata(str(self.root), self.lineage, self.generation)

            # Upload apex checkpoint specifically
            apex_link = self.ckpt_dir / "apex.pt"
            if apex_link.exists():
                resolved = apex_link.resolve()
                s3_key = f"ltee_archive/{self.lineage}/gen_{self.generation:03d}/checkpoints/{resolved.name}"
                uploader.upload_checkpoint(str(resolved), s3_key)

            # Upload safely-backed-up SQLite registry
            uploader.safe_upload_sqlite(self.root / "registry.sqlite")

            print(f"  [{self.lineage}] S3 upload complete (bucket: {bucket})")
        except Exception as e:
            print(f"  [{self.lineage}] S3 upload failed (local files safe): {e}")

    def _save_gen_meta(self):
        meta_path = self.gen_dir / "gen_meta.json"
        with open(meta_path, "w") as f:
            json.dump(self._gen_meta, f, indent=2)

    def _update_apex_hall(self, meta: CheckpointMeta):
        hall_path = self.root / "apex_hall.json"
        if hall_path.exists():
            hall = json.loads(hall_path.read_text())
        else:
            hall = {"per_lineage_best": {}, "global_best": None, "updated": None}

        entry = {
            "gen": meta.generation, "epoch": meta.epoch,
            "calmar": meta.metrics.get("calmar_ratio"),
            "pnl": meta.metrics.get("pnl"),
            "path": meta.file_path,
        }

        # Update per-lineage best
        current = hall["per_lineage_best"].get(meta.lineage)
        if current is None or (entry["calmar"] or 0) > (current.get("calmar") or 0):
            hall["per_lineage_best"][meta.lineage] = entry

        # Update global best
        if hall["global_best"] is None or (entry["calmar"] or 0) > (hall["global_best"].get("calmar") or 0):
            hall["global_best"] = {"lineage": meta.lineage, **entry}

        hall["updated"] = datetime.now(timezone.utc).isoformat()
        with open(hall_path, "w") as f:
            json.dump(hall, f, indent=2)

    @staticmethod
    def resurrect(checkpoint_path, perception_engine, ppo_agent, optimizer,
                  scaler=None, device="cuda"):
        """Revive a frozen checkpoint — the digital thaw protocol.

        Restores model weights, optimizer state, and all four RNG states
        for exact training reproduction from any historical point.
        """
        ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)

        missing, unexpected = perception_engine.load_state_dict(ckpt["perception_state_dict"], strict=False)
        if missing:
            print(f"  ⚠️ New perception params in checkpoint (init random): {missing}")
        if unexpected:
            print(f"  ⚠️ Unexpected perception params in checkpoint (ignored): {unexpected}")
        ppo_agent.load_state_dict(ckpt["ppo_agent_state_dict"])
        optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        if scaler and ckpt.get("scaler_state_dict"):
            scaler.load_state_dict(ckpt["scaler_state_dict"])

        # Restore RNG states for exact reproduction
        rng = ckpt["rng_states"]
        torch.set_rng_state(rng["torch_cpu"])
        if rng["torch_cuda"] and torch.cuda.is_available():
            torch.cuda.set_rng_state_all(rng["torch_cuda"])
        np.random.set_state(tuple(rng["numpy"]))  # numpy state is a tuple
        random.setstate(tuple(rng["python"]))

        return {
            "epoch": ckpt["epoch"],
            "generation": ckpt["generation"],
            "lineage": ckpt["lineage"],
            "phase": ckpt["curriculum_phase"],
            "metrics": ckpt["metrics"],
            "env_params": ckpt["env_params"],
        }
