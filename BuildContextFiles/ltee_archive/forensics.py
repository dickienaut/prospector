"""Forensic analysis interface — the digital competition assay.

Provides query and comparison tools for analyzing agent evolution
across time, lineages, and generations.
"""

import sqlite3
from pathlib import Path

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


class ForensicAnalyzer:

    def __init__(self, archive_root):
        self.root = Path(archive_root)
        self.db = sqlite3.connect(str(self.root / "registry.sqlite"), check_same_thread=False)
        self.db.row_factory = sqlite3.Row

    def compare_checkpoints(self, ckpt_id_a, ckpt_id_b):
        """Head-to-head comparison of two checkpoints."""
        a = dict(self.db.execute(
            "SELECT * FROM checkpoints WHERE checkpoint_id = ?", (ckpt_id_a,)
        ).fetchone())
        b = dict(self.db.execute(
            "SELECT * FROM checkpoints WHERE checkpoint_id = ?", (ckpt_id_b,)
        ).fetchone())

        metric_cols = ["pnl", "calmar_ratio", "max_drawdown", "trade_count", "action_entropy"]
        diff = {}
        for col in metric_cols:
            va, vb = a.get(col), b.get(col)
            if va is not None and vb is not None:
                diff[col] = {"a": va, "b": vb, "delta": vb - va}

        return {"a": a, "b": b, "diff": diff}

    def lineage_trajectory(self, lineage):
        """Full fitness trajectory across all generations for a lineage."""
        assert HAS_PANDAS, "pandas required for trajectory analysis"
        return pd.read_sql_query("""
            SELECT generation, epoch, pnl, calmar_ratio, max_drawdown,
                   action_entropy, friction_scale, curriculum_phase, snapshot_reason
            FROM checkpoints WHERE lineage_id = ?
            ORDER BY generation, epoch
        """, self.db, params=(lineage,))

    def cross_lineage_at_epoch(self, epoch):
        """Compare all lineages at a specific epoch (nearest available)."""
        assert HAS_PANDAS, "pandas required"
        return pd.read_sql_query("""
            SELECT c.* FROM checkpoints c
            INNER JOIN (
                SELECT lineage_id, epoch, MIN(ABS(epoch - ?)) as dist
                FROM checkpoints GROUP BY lineage_id
                HAVING dist = MIN(ABS(epoch - ?))
            ) nearest ON c.lineage_id = nearest.lineage_id AND c.epoch = nearest.epoch
        """, self.db, params=(epoch, epoch))

    def generational_drift(self, lineage):
        """Compare apex performance across respawn generations."""
        assert HAS_PANDAS, "pandas required"
        return pd.read_sql_query("""
            SELECT generation, spawn_reason, apex_epoch, apex_calmar, apex_pnl,
                   death_epoch, death_reason, graduated
            FROM generations WHERE lineage_id = ?
            ORDER BY generation
        """, self.db, params=(lineage,))

    def extinction_report(self):
        """List all Auto-Executioner kills across all lineages."""
        assert HAS_PANDAS, "pandas required"
        return pd.read_sql_query("""
            SELECT lineage_id, generation, death_epoch, death_reason,
                   apex_calmar, apex_pnl, started_at, ended_at
            FROM generations WHERE death_reason IS NOT NULL
            ORDER BY lineage_id, generation
        """, self.db)

    def global_apex_ranking(self, top_n=10):
        """Rank all apex checkpoints across all lineages and generations."""
        assert HAS_PANDAS, "pandas required"
        return pd.read_sql_query("""
            SELECT checkpoint_id, lineage_id, generation, epoch,
                   calmar_ratio, pnl, max_drawdown, file_path
            FROM checkpoints WHERE calmar_ratio IS NOT NULL
            ORDER BY calmar_ratio DESC LIMIT ?
        """, self.db, params=(top_n,))

    def load_telemetry(self, lineage, generation):
        """Load full epoch-by-epoch telemetry for a generation."""
        assert HAS_PANDAS, "pandas required"
        path = self.root / lineage / f"gen_{generation:03d}" / "telemetry.jsonl"
        return pd.read_json(path, lines=True)

    def close(self):
        self.db.close()
