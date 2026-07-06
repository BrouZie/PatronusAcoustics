import numpy as np

from .constants import saturation_vapor_pressure_kPa


class AtmosphericAbsorption:
    """ISO 9613-1 atmospheric sound absorption coefficient.

    Computes the frequency-dependent attenuation coefficient
    α(f, T, RH, P) in dB/m per ISO 9613-1 / ANSI S1.26-1995.
    """

    T0 = 293.15
    P_ref = 101.325
    T01 = 273.16

    def __init__(self, temperature_C=20.0, humidity_pct=50.0, pressure_kPa=101.325):
        self.temperature_C = temperature_C
        self.humidity_pct = humidity_pct
        self.pressure_kPa = pressure_kPa
        self._update()

    def _update(self):
        T_K = self.temperature_C + 273.15
        P = self.pressure_kPa

        # ISO 9613-1 wants h as molar concentration of water vapour in
        # PERCENT: h = RH% · Psat / Pa (saturation expression shared with
        # the Cramer sound-speed formula in constants.py).
        h = self.humidity_pct * saturation_vapor_pressure_kPa(
            self.temperature_C) / P

        f_rO = (P / self.P_ref) * (24.0 + 4.04e4 * h * (0.02 + h) / (0.391 + h))

        # Temperature ratios use absolute temperature (T/T0 with T0 = 293.15 K).
        Tr = T_K / self.T0
        d = Tr ** (-1.0 / 3.0) - 1.0
        f_rN = (P / self.P_ref) * Tr ** (-0.5) * (
            9.0 + 280.0 * h * np.exp(-4.17 * d)
        )

        self._T_K = T_K
        self._h = h
        self._f_rO = f_rO
        self._f_rN = f_rN

    def coefficient(self, f):
        """Attenuation coefficient α in dB/m.

        Parameters
        ----------
        f : ndarray
            Frequencies in Hz.

        Returns
        -------
        alpha : ndarray
            Attenuation in dB/m, same shape as f.
        """
        f = np.asarray(f, dtype=float)
        T = self.temperature_C + 273.15
        f_sq = f ** 2

        term1 = 1.84e-11 * (self.P_ref / self.pressure_kPa) * np.sqrt(T / self.T0)

        term2 = (T / self.T0) ** (-2.5) * (
            0.01275 * np.exp(-2239.1 / T) / (self._f_rO + f_sq / self._f_rO)
            + 0.1068 * np.exp(-3352.0 / T) / (self._f_rN + f_sq / self._f_rN)
        )

        alpha = 8.686 * f_sq * (term1 + term2)
        return alpha

    def pressure_filter(self, f, distance):
        """Pressure attenuation factor exp(-α·d / 8.686).

        Parameters
        ----------
        f : ndarray
            Frequencies in Hz.
        distance : float
            Propagation distance in meters.

        Returns
        -------
        H : ndarray
            Real-valued attenuation factor, same shape as f.
        """
        alpha = self.coefficient(f)
        return np.exp(-alpha * distance / 8.686)

    def set_conditions(self, temperature_C, humidity_pct, pressure_kPa):
        self.temperature_C = temperature_C
        self.humidity_pct = humidity_pct
        self.pressure_kPa = pressure_kPa
        self._update()

    def effective_attenuation_db(self, f, distance):
        """Total attenuation in dB over a given distance.

        Convenience method: α(f) × distance.
        """
        return self.coefficient(f) * distance
