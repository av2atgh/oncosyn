"""Phase III ORR forecasts from the oncosyn Phase II -> III calibration.

Calibration (report_2026, 157 matched pairs; reports/agreement.csv):
    ORR_III = A + B * ORR_II,  Bland-Altman 95% limits of agreement LOA.
Combinations: Phase II input = Bliss expectation 1 - prod(1 - p_i).
Run: python3 forecasts/forecast.py
"""
A, B = 0.23044, 0.41759          # calibration intercept, slope
LOA = (-0.5950, 0.4325)          # Bland-Altman limits (Phase II - Phase III)


def calibrate(orr2):
    point = A + B * orr2
    # Phase III = Phase II - d, d in LOA  ->  band on the Phase III value
    lo, hi = max(0.0, orr2 - LOA[1]), min(1.0, orr2 - LOA[0])
    return point, lo, hi


def bliss(*p):
    q = 1.0
    for x in p:
        q *= 1.0 - x
    return 1.0 - q


# single-agent inputs
DARA_2L_PDAC_III = 0.332   # RASolute 302, daraxonrasib arm ORR
GEM = 0.081                # oncosyn pooled single-agent gemcitabine (n=3 arms)
NAB = 0.191                # oncosyn pooled single-agent nab-paclitaxel (n=4 arms)

if __name__ == "__main__":
    gnp = bliss(GEM, NAB)
    combo = bliss(DARA_2L_PDAC_III, GEM, NAB)
    print(f"Bliss GnP = {gnp:.3f}; Bliss daraxonrasib+GnP = {combo:.3f}")
    for label, x in [("F1 RASolute 303, daraxonrasib+GnP (1L PDAC)", combo),
                     ("F2 RASolve 301, daraxonrasib (2L NSCLC), ORR_II=0.30", 0.30),
                     ("F2 RASolve 301, daraxonrasib (2L NSCLC), ORR_II=0.38", 0.38),
                     ("check: RASolute 302, ORR_II=0.35 (observed III 0.332)", 0.35)]:
        pt, lo, hi = calibrate(x)
        print(f"{label}: point {pt:.3f}, band [{lo:.2f}, {hi:.2f}]")
