"""Physical constants and numerical guards shared across the simulation.

Every module must take the speed of sound from here (or via constructor
injection from Simulation) so that geometry steering, propagation delays,
and image-source paths always agree.
"""

import math

# Speed of sound at ~20 °C. Used wherever no atmospheric config is available
# (environment disabled, standalone tools) to keep legacy numerics.
SPEED_OF_SOUND_REF = 343.0

# SPL of a 1 Pa RMS tone re 20 µPa; reference for mic EIN/SNR specs.
REF_SPL_DB = 94.0

# Reference pressure for SPL (20 µPa RMS). The calibrated signal path
# (active when signal.snr_db is None) carries acoustic pressure in Pa
# up to SensorModel, which converts to digital full scale last.
PA_REF = 20e-6

# Numerical guards (regularization floors).
EPS_DISTANCE = 1e-6   # 1/r attenuation floor
EPS_NORM = 1e-10      # vector-norm / PHAT-magnitude floor
EPS_LOG = 1e-30       # log/power floor

AIR_DENSITY = 1.2     # kg/m³ (rho0, Delany-Bazley ground model)


def saturation_vapor_pressure_kPa(temperature_C: float) -> float:
    """Saturation vapor pressure of water (kPa), ISO 9613-1 expression.

    Shared by the absorption model and the Cramer sound-speed formula so
    both use the same humidity physics.
    """
    T_K = temperature_C + 273.15
    C = -6.8346 * (273.16 / T_K) ** 1.261 + 4.6151
    return 101.325 * 10.0 ** C


# Cramer (1993), JASA 93(5) 2510-2516: c(t, p, x_w, x_c) polynomial,
# valid 0-30 °C, 75-102 kPa. t in °C, p in Pa, mole fractions unitless.
_CRAMER_A = (
    331.5024, 0.603055, -0.000528,          # a0  + a1·t  + a2·t²
    51.471935, 0.1495874, -0.000782,        # (a3 + a4·t  + a5·t²)·x_w
    -1.82e-7, 3.73e-8, -2.93e-10,           # (a6 + a7·t  + a8·t²)·p
    -85.20931, -0.228525, 5.91e-5,          # (a9 + a10·t + a11·t²)·x_c
    -2.835149, -2.15e-13, 29.179762,        # a12·x_w² + a13·p² + a14·x_c²
    0.000486,                               # a15·x_w·p·x_c
)


def speed_of_sound(temperature_C: float = 20.0,
                   humidity_pct: float | None = None,
                   pressure_kPa: float = 101.325,
                   co2_mole_fraction: float = 4.0e-4) -> float:
    """Speed of sound in air (m/s).

    Without humidity: the legacy dry-air formula, bit-for-bit (used when
    the environment is disabled and by older configs). With humidity:
    Cramer (1993) including pressure and CO2 terms — worth ~+0.8 m/s at
    20 °C / 50 % RH over dry air, which is a ~0.2 % TDOA scale shift.
    """
    if humidity_pct is None:
        return 331.3 * math.sqrt(1.0 + temperature_C / 273.15)

    t = temperature_C
    p = pressure_kPa * 1000.0  # Pa
    p_sat = saturation_vapor_pressure_kPa(t) * 1000.0
    # Enhancement factor for moist air over the ideal Dalton mixture.
    f_enh = 1.00062 + 3.14e-8 * p + 5.6e-7 * t * t
    x_w = (humidity_pct / 100.0) * f_enh * p_sat / p
    x_c = co2_mole_fraction

    a = _CRAMER_A
    return (a[0] + a[1] * t + a[2] * t * t
            + (a[3] + a[4] * t + a[5] * t * t) * x_w
            + (a[6] + a[7] * t + a[8] * t * t) * p
            + (a[9] + a[10] * t + a[11] * t * t) * x_c
            + a[12] * x_w * x_w + a[13] * p * p + a[14] * x_c * x_c
            + a[15] * x_w * p * x_c)


def spl_to_pa(spl_db: float) -> float:
    """RMS pressure (Pa) of a level in dB SPL re 20 µPa."""
    return PA_REF * 10.0 ** (spl_db / 20.0)


def pa_to_spl(p_rms: float) -> float:
    """Level in dB SPL re 20 µPa of an RMS pressure (Pa)."""
    return 20.0 * math.log10(max(p_rms, 1e-30) / PA_REF)
