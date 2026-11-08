from brain.evolution import evaluate_candidate


BASE = dict(quality=0.7, errors=2, latency=100)


def test_quality_gain():
    assert evaluate_candidate(baseline=BASE, candidate=dict(quality=0.75, errors=2, latency=105), iteration=1, model_calls=2, cost_usd=.1).accepted


def test_runaway_loop_stops():
    assert not evaluate_candidate(baseline=BASE, candidate=dict(quality=.9, errors=0, latency=50), iteration=4, model_calls=2, cost_usd=.1).accepted


def test_owner_gate():
    result = evaluate_candidate(baseline=BASE, candidate=BASE, iteration=1, model_calls=0, cost_usd=0, action="production_deploy")
    assert result.needs_owner_approval


def test_regression_rejected():
    assert not evaluate_candidate(baseline=BASE, candidate=dict(quality=.9, errors=3, latency=100), iteration=1, model_calls=1, cost_usd=.1).accepted
