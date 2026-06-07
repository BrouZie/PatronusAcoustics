import numpy as np


class RefractionModel:
    """Atmospheric refraction from wind and temperature gradients.

    Computes excess attenuation due to upward/downward refraction
    using an effective sound speed profile.

    Wind profile: logarithmic (Monin-Obukhov).
    Temperature profile: linear lapse rate.
    Effective sound speed: c_eff(z) = c(T(z)) + u(z)·cos(θ_source_to_receiver)
    """

    C0 = 343.0

    def __init__(self, wind_shear_ms_per_m=0.0,
                 temperature_lapse_rate=-0.0065,
                 reference_height=5.0,
                 roughness_length=0.03):
        self.wind_shear_ms_per_m = wind_shear_ms_per_m
        self.temperature_lapse_rate = temperature_lapse_rate
        self.reference_height = reference_height
        self.roughness_length = roughness_length

    def wind_profile(self, z, u_ref):
        if u_ref <= 0 or z <= self.roughness_length:
            return 0.0
        return u_ref * np.log(z / self.roughness_length) / np.log(
            self.reference_height / self.roughness_length
        )

    def temperature_profile(self, z, T0_C):
        return T0_C + self.temperature_lapse_rate * z

    def sound_speed(self, T_C):
        return 331.3 * np.sqrt(1.0 + T_C / 273.15)

    def effective_sound_speed(self, z, T0_C, u_ref, cos_theta=1.0):
        T_z = self.temperature_profile(z, T0_C)
        c_z = self.sound_speed(T_z)
        u_z = self.wind_profile(z, u_ref)
        return c_z + u_z * cos_theta

    def excess_attenuation(self, source_height, receiver_height,
                           distance, T0_C=20.0, u_ref=0.0, cos_theta=1.0,
                           frequencies=None):
        """Excess attenuation in dB from refraction.

        Computes an approximate excess attenuation when the source is
        in a refractive shadow zone. Downward refraction (positive gradient)
        returns 0 dB. Upward refraction returns frequency-dependent loss.
        Accepts a scalar or array of *frequencies* (Hz) to return
        frequency-dependent excess loss.

        References:
            - Attenborough et al., "Predicting Outdoor Sound" (2007)
            - ISO 9613-2 shadow zone formulation
        """
        z_rec = max(receiver_height, 0.1)
        z_src = max(source_height, 0.1)

        if z_rec <= self.roughness_length or z_src <= self.roughness_length:
            return _zero_like(frequencies)

        z_mid = np.sqrt(z_rec * z_src)

        c_eff_rec = self.effective_sound_speed(z_rec, T0_C, u_ref, cos_theta)
        c_eff_src = self.effective_sound_speed(z_src, T0_C, u_ref, cos_theta)
        c_eff_mid = self.effective_sound_speed(z_mid, T0_C, u_ref, cos_theta)

        if z_mid > 0.1:
            dc_dz = (c_eff_mid - c_eff_rec) / max(z_mid - z_rec, 0.1)
        else:
            dc_dz = 0.0

        if dc_dz >= -1e-6:
            return _zero_like(frequencies)

        R_curvature = 1.0 / (-dc_dz / c_eff_mid + 1e-10)

        shadow_dist = np.sqrt(2.0 * R_curvature * z_src)
        if distance < shadow_dist * 0.8:
            return _zero_like(frequencies)

        frac = distance / max(shadow_dist, 1.0)
        if frac <= 1.0:
            return _zero_like(frequencies)

        A_frac = 1.0 - 1.0 / frac
        if A_frac < 0:
            A_frac = 0.0

        if frequencies is None:
            return min((3.0 + 0.01) * A_frac ** 2, 15.0)

        frequencies = np.asarray(frequencies, dtype=float)
        max_excess = 3.0 + 0.01 * frequencies / 1000.0
        return np.minimum(max_excess * A_frac ** 2, 15.0)


def _zero_like(frequencies):
    if frequencies is None:
        return 0.0
    return np.zeros_like(frequencies, dtype=float)
