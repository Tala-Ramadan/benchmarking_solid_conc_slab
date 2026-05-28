import math

"""
acoustics.py
============

Acoustic performance checks per DIN 4109 (German acoustic standard).

This module provides calculations for:
- Airborne sound insulation (R'w)
- Impact sound level (L'n,w)
- Floor system acoustic performance including:
  - Structural floor
  - Footfall sound insulation
  - Floating screed
"""


def calc_dRw_table(f0: float, Rw0: float) -> float:
    """
    Berechnet ΔR_w nach DIN 4109-34:2016-07 Tab. 1.

    Verwendet konservativ die nächsthöhere Schwelle (mehr negative Werte).
    Beispiel: f0 = 350 Hz → verwendet -7 dB (Schwelle bei 400 Hz).

    Parameters
    ----------
    f0 : float
        Resonanzfrequenz der Vorsatzkonstruktion [Hz].
    Rw0 : float
        Luftschalldämm-Maß der Rohdecke [dB].

    Returns
    -------
    float
        ΔR_w [dB].

    Raises
    ------
    ValueError
        Wenn f0 außerhalb des zulässigen Bereichs liegt.
    """
    if f0 <= 30.0:
        f0 = 30.0
    if f0 > 5000.0:
        raise ValueError(f"f0 = {f0} Hz > 5000 Hz (maximum allowed)")

    # Tabelle DIN 4109-34:2016-07 Tab. 1
    # Konservativ: verwende nächsthöhere Schwelle (mehr negative Werte)

    if f0 <= 160.0:
        return max(74.4 - 20.0 * math.log10(f0) - 0.5 * Rw0, 0.0)
    if f0 <= 200.0:
        return -1.0
    if f0 <= 250.0:
        return -3.0
    if f0 <= 315.0:
        return -5.0
    if f0 <= 400.0:
        return -7.0
    if f0 <= 500.0:
        return -9.0
    if f0 <= 1600.0:
        return -10.0  # covers 500<f0<=630 conservatively too (630..1600 is -10)
    return -5.0  # 1600<f0<=5000


def calc_Rw_prime_concrete_slab(m1: float, m2: float, s_dyn: float) -> float:
    """
    Berechnet das bewertete Luftschalldämm-Maß R'w einer Stahlbetondecke
    mit schwimmendem Estrich nach DIN 4109-32/-34 (vereinfachtes Verfahren).

    Parameter
    ---------
    m1 : float
        Flächenbezogene Masse der Rohdecke (kg/m²).
    m2 : float
        Flächenbezogene Masse der Estrichplatte (kg/m²).
    s_dyn : float
        Dynamische Steifigkeit der Dämmschicht (MN/m³).

    Returns
    -------
    float
        R'w in dB.
    """
    # Hard-coded safety factor for flanking transmission, execution, etc.
    U_PROG_R = 2.0  # # safety factor according to DIN 4109-2:2018-01, Equ. (49)

    # 1) Rohdecken-Luftschalldämmung
    if m1 < 65.0:
        raise ValueError("Specific mass of slab must be greater than 65 kg/m².")
    if m1 > 720.0:
        m1 = 720.0  # limit m1 to 720 kg/m² according to Fischer 2019: Handbuch zu DIN 4109
    Rw0 = 30.9 * math.log10(m1) - 22.2  # DIN 4109-32:2016-07 Equ. (13)

    # 2) Resonanzfrequenz des schwimmenden Estrichs
    f0 = 160.0 * math.sqrt(s_dyn * (1.0 / m1 + 1.0 / m2))  # DIN 4109-34:2016-07 Equ. (1)

    # 3) Luftschall-Verbesserung der Vorsatzkonstruktion
    dRw = calc_dRw_table(f0, Rw0)  # DIN 4109-34:2016-07 Tab. 1

    # 4) Gesamtes Rw der Decke (Direktweg)
    Rw_deck = Rw0 + dRw

    # 5) Feldgrösse R'w mit pauschalem Abschlag
    Rw_prime = Rw_deck - U_PROG_R
    return Rw_prime


def calc_Ln_prime_concrete_slab(m1, m2, s_dyn) -> float:
    """
    Berechnet den bewerteten Norm-Trittschallpegel L'n,w einer
    Stahlbetondecke mit schwimmendem Estrich nach DIN 4109-32/-34
    (vereinfachtes Verfahren).

    Parameter
    ---------
    m1 : float
        Flächenbezogene Masse der Rohdecke (kg/m²).
    m2 : float
        Flächenbezogene Masse der Estrichplatte (kg/m²).
    s_dyn : float
        Dynamische Steifigkeit der Dämmschicht (MN/m³).

    Returns
    -------
    float
        L'n,w in dB.
    """
    # Hard-coded safety factor for flanking transmission, execution, etc.
    U_PROG_L = 3.0  # safety factor according to DIN 4109-2:2018-01, Equ. (53)

    # 1) Äquivalenter Norm-Trittschallpegel der Rohdecke
    Ln_eq0 = 164.0 - 35.0 * math.log10(m1)  # m0' = 1 kg/m²

    # 2) Trittschallminderung des schwimmenden Estrichs
    dLw = 13.0 * math.log10(m2) - 14.2 * math.log10(s_dyn) + 20.8

    # 3) Deckenpegel (Direktweg)
    Ln_deck = Ln_eq0 - dLw

    # 4) Feldgrösse L'n,w mit pauschalem Zuschlag
    Ln_prime = Ln_deck + U_PROG_L
    return Ln_prime
