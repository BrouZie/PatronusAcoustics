from .detection_range import RangeCurve, range_at_rate, run_range_curve
from .mcu_budget import McuBudget, estimate_from_config
from .mcu_profiles import BUILTIN_PROFILES, mics_per_bus, required_tdm_buses
from .mcu_requirements import (
    McuReport,
    McuRequirements,
    ProfileVerdict,
    StageRequirement,
    compute_requirements,
    evaluate_from_config,
)
from .triangulation import position_error_map, triangulate

__all__ = [
    "RangeCurve", "range_at_rate", "run_range_curve",
    "McuBudget", "estimate_from_config",
    "BUILTIN_PROFILES", "mics_per_bus", "required_tdm_buses",
    "McuReport", "McuRequirements", "ProfileVerdict", "StageRequirement",
    "compute_requirements", "evaluate_from_config",
    "position_error_map", "triangulate",
]
