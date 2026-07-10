from .detection_range import RangeCurve, range_at_rate, run_range_curve
from .mcu_profiles import BUILTIN_PROFILES, mics_per_bus, required_tdm_buses
from .mcu_requirements import (
    McuReport,
    McuRequirements,
    ProfileVerdict,
    RamContribution,
    StageRequirement,
    StageWork,
    compute_requirements,
    evaluate_from_config,
    evaluate_profile,
    reference_stage_cycles,
)
from .triangulation import position_error_map, triangulate

__all__ = [
    "RangeCurve", "range_at_rate", "run_range_curve",
    "BUILTIN_PROFILES", "mics_per_bus", "required_tdm_buses",
    "McuReport", "McuRequirements", "ProfileVerdict", "StageRequirement",
    "StageWork", "RamContribution",
    "compute_requirements", "evaluate_from_config", "evaluate_profile",
    "reference_stage_cycles",
    "position_error_map", "triangulate",
]
