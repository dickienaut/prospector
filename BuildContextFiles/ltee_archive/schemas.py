"""Typed metadata containers for the Lenski Ledger archival system."""

from dataclasses import dataclass, asdict
from typing import Optional
from enum import Enum


class CurriculumPhase(Enum):
    EMBRYONIC = "Embryonic"
    JUVENILE = "Juvenile"
    ADULT = "Adult"


class SnapshotReason(Enum):
    CRUISING = "cruising"
    TRANSITION_ZONE = "transition_zone"
    APEX = "apex"
    FINAL = "final"
    PLATEAU_ADVANCE = "plateau_advance"
    MANUAL = "manual"


class DeathReason(Enum):
    DRAWDOWN_EXCEEDED = "drawdown_exceeded"
    LOSS_DIVERGENCE = "loss_divergence"
    MANUAL_KILL = "manual_kill"


@dataclass
class EpochMetrics:
    pnl: float
    trade_count: int
    avg_cost_per_trade: float
    max_drawdown: float
    calmar_ratio: Optional[float]
    action_entropy: float
    policy_std: float
    jitter_filter_rate: float


@dataclass
class EnvParams:
    friction_scale: float
    latency_ticks: int
    direction_reward_weight: float
    entropy_coefficient: float


@dataclass
class CheckpointMeta:
    checkpoint_id: str
    lineage: str
    generation: int
    epoch: int
    phase: str  # CurriculumPhase.value
    reason: str  # SnapshotReason.value
    wall_time: str
    sha256: str
    file_size: int
    file_path: str
    is_apex: bool
    metrics: dict  # asdict(EpochMetrics)
    env_params: dict  # asdict(EnvParams)
