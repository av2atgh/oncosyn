from phase2.analyze.stats import bliss_expected


def test_expected_orr_single_agent():
    assert abs(bliss_expected([0.3]) - 0.3) < 1e-9


def test_expected_orr_two_agents():
    # 1 - (1-0.3)(1-0.4) = 0.58
    assert abs(bliss_expected([0.3, 0.4]) - 0.58) < 1e-9


def test_expected_orr_monotonic_lower_bound():
    # adding an agent cannot lower the expected combination ORR
    assert bliss_expected([0.3, 0.4, 0.2]) >= bliss_expected([0.3, 0.4])
