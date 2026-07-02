"""Curriculum-aware adaptive snapshot density engine.

Inspired by LTEE's 500-generation fixed interval with additional density
at environmental shift events. Concentrates checkpoints where the cosine
annealer creates maximum policy stress.
"""

from .schemas import SnapshotReason, CurriculumPhase, EpochMetrics


class AdaptiveSnapshotPolicy:
    """Three-tier snapshot scheduling:

    1. Cruising altitude: every 100 epochs during stable phases
    2. Transition zones: every 10 epochs during phase boundaries (480-620, 1400-1600)
    3. Apex predator: whenever a new best metric is achieved (Adult phase)
    """

    def __init__(self, phase_1_end=500, phase_2_end=1500, total_epochs=3000,
                 transition_margin=20, transition_interval=10,
                 cruising_interval=100, apex_metric="calmar_ratio"):
        self.phase_1_end = phase_1_end
        self.phase_2_end = phase_2_end
        self.total_epochs = total_epochs
        self.transition_interval = transition_interval
        self.cruising_interval = cruising_interval
        self.apex_metric = apex_metric

        # Transition zones: margin epochs before and after each phase boundary
        self.transition_zones = [
            (phase_1_end - transition_margin, phase_1_end + transition_margin * 6),  # 480-620
            (phase_2_end - cruising_interval, phase_2_end + cruising_interval),      # 1400-1600
        ]

        # Apex tracking
        self.best_apex_value = float('-inf')
        self.best_apex_epoch = None

    def should_save(self, epoch: int, metrics: EpochMetrics) -> tuple:
        """Returns (should_save: bool, reason: SnapshotReason | None).

        Called every epoch. The archiver decides whether to write a full checkpoint.
        """
        # Final epoch always saves
        if epoch >= self.total_epochs:
            return True, SnapshotReason.FINAL

        # Apex predator: only track during Adult phase
        if epoch >= self.phase_2_end:
            current_val = getattr(metrics, self.apex_metric, None)
            if current_val is not None and current_val > self.best_apex_value:
                self.best_apex_value = current_val
                self.best_apex_epoch = epoch
                return True, SnapshotReason.APEX

        # Transition zones: dense saves near phase boundaries
        for zone_start, zone_end in self.transition_zones:
            if zone_start <= epoch <= zone_end:
                if epoch % self.transition_interval == 0:
                    return True, SnapshotReason.TRANSITION_ZONE
                return False, None

        # Cruising altitude: standard heartbeat
        if epoch % self.cruising_interval == 0:
            return True, SnapshotReason.CRUISING

        return False, None

    def get_phase(self, epoch: int) -> CurriculumPhase:
        if epoch < self.phase_1_end:
            return CurriculumPhase.EMBRYONIC
        elif epoch < self.phase_2_end:
            return CurriculumPhase.JUVENILE
        else:
            return CurriculumPhase.ADULT
