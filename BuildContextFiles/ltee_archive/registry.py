"""SQLite-backed metadata registry for the Lenski Ledger.

Provides queryable index over checkpoint files, generation genealogy,
and lineage history. No weights stored — only metadata and file paths.
"""

import sqlite3
from pathlib import Path
from .schemas import CheckpointMeta


class FossilRegistry:

    SCHEMA_VERSION = 1

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent read/write
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS lineages (
                lineage_id    TEXT PRIMARY KEY,
                instrument    TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                status        TEXT DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS generations (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                lineage_id    TEXT NOT NULL REFERENCES lineages(lineage_id),
                generation    INTEGER NOT NULL,
                spawn_reason  TEXT NOT NULL,
                parent_gen    INTEGER,
                started_at    TEXT NOT NULL,
                ended_at      TEXT,
                death_epoch   INTEGER,
                death_reason  TEXT,
                graduated     BOOLEAN DEFAULT FALSE,
                dna_hash      TEXT NOT NULL,
                apex_epoch    INTEGER,
                apex_calmar   REAL,
                apex_pnl      REAL,
                UNIQUE(lineage_id, generation)
            );

            CREATE TABLE IF NOT EXISTS checkpoints (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_id   TEXT UNIQUE NOT NULL,
                lineage_id      TEXT NOT NULL,
                generation      INTEGER NOT NULL,
                epoch           INTEGER NOT NULL,
                curriculum_phase TEXT NOT NULL,
                snapshot_reason TEXT NOT NULL,
                wall_time       TEXT NOT NULL,
                file_path       TEXT NOT NULL,
                file_size       INTEGER NOT NULL,
                sha256          TEXT NOT NULL,
                is_apex         BOOLEAN DEFAULT FALSE,
                pnl             REAL,
                calmar_ratio    REAL,
                max_drawdown    REAL,
                trade_count     INTEGER,
                action_entropy  REAL,
                policy_std      REAL,
                friction_scale  REAL,
                latency_ticks   INTEGER,
                direction_reward_wt  REAL,
                entropy_coefficient  REAL,
                FOREIGN KEY (lineage_id, generation) REFERENCES generations(lineage_id, generation)
            );

            CREATE INDEX IF NOT EXISTS idx_ckpt_lineage_gen
                ON checkpoints(lineage_id, generation, epoch);
            CREATE INDEX IF NOT EXISTS idx_ckpt_apex
                ON checkpoints(is_apex) WHERE is_apex = TRUE;
            CREATE INDEX IF NOT EXISTS idx_ckpt_phase
                ON checkpoints(curriculum_phase, epoch);

            CREATE TABLE IF NOT EXISTS apex_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                lineage_id      TEXT NOT NULL,
                checkpoint_id   TEXT NOT NULL,
                calmar_ratio    REAL,
                pnl             REAL,
                recorded_at     TEXT NOT NULL,
                superseded_by   TEXT
            );
        """)
        self.conn.commit()

    def ensure_lineage(self, lineage_id: str, instrument: str, created_at: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO lineages (lineage_id, instrument, created_at) VALUES (?, ?, ?)",
            (lineage_id, instrument, created_at)
        )
        self.conn.commit()

    def register_generation(self, lineage_id, generation, spawn_reason, parent_gen, dna_hash, started_at):
        self.conn.execute("""
            INSERT OR REPLACE INTO generations
            (lineage_id, generation, spawn_reason, parent_gen, dna_hash, started_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (lineage_id, generation, spawn_reason, parent_gen, dna_hash, started_at))
        self.conn.commit()

    def max_generation(self, lineage_id):
        """Highest generation recorded for a lineage, or None if the lineage is new."""
        row = self.conn.execute(
            "SELECT MAX(generation) AS g FROM generations WHERE lineage_id = ?",
            (lineage_id,)
        ).fetchone()
        return row["g"] if row and row["g"] is not None else None

    def register_checkpoint(self, meta: CheckpointMeta):
        m = meta.metrics
        e = meta.env_params
        self.conn.execute("""
            INSERT INTO checkpoints
            (checkpoint_id, lineage_id, generation, epoch, curriculum_phase,
             snapshot_reason, wall_time, file_path, file_size, sha256, is_apex,
             pnl, calmar_ratio, max_drawdown, trade_count, action_entropy, policy_std,
             friction_scale, latency_ticks, direction_reward_wt, entropy_coefficient)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            meta.checkpoint_id, meta.lineage, meta.generation, meta.epoch,
            meta.phase, meta.reason, meta.wall_time, meta.file_path,
            meta.file_size, meta.sha256, meta.is_apex,
            m.get("pnl"), m.get("calmar_ratio"), m.get("max_drawdown"),
            m.get("trade_count"), m.get("action_entropy"), m.get("policy_std"),
            e.get("friction_scale"), e.get("latency_ticks"),
            e.get("direction_reward_weight"), e.get("entropy_coefficient"),
        ))
        self.conn.commit()

    def record_death(self, lineage_id, generation, death_epoch, death_reason, ended_at):
        self.conn.execute("""
            UPDATE generations SET death_epoch = ?, death_reason = ?, ended_at = ?
            WHERE lineage_id = ? AND generation = ?
        """, (death_epoch, death_reason, ended_at, lineage_id, generation))
        self.conn.commit()

    def record_graduation(self, lineage_id, generation, ended_at):
        self.conn.execute("""
            UPDATE generations SET graduated = TRUE, ended_at = ?
            WHERE lineage_id = ? AND generation = ?
        """, (ended_at, lineage_id, generation))
        self.conn.commit()

    def update_generation_apex(self, lineage_id, generation, apex_epoch, apex_calmar, apex_pnl):
        self.conn.execute("""
            UPDATE generations SET apex_epoch = ?, apex_calmar = ?, apex_pnl = ?
            WHERE lineage_id = ? AND generation = ?
        """, (apex_epoch, apex_calmar, apex_pnl, lineage_id, generation))
        self.conn.commit()

    def close(self):
        self.conn.close()
