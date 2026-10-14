from agents.runtime import AGENTS, run_specialists


def test_specialist_catalog_has_distinct_roles():
    ids = [agent["id"] for agent in AGENTS]
    assert len(ids) == len(set(ids))
    assert {"qualification", "market", "audit", "offer", "sales", "qa"} == set(ids)


def test_runtime_rejects_unknown_agents_before_provider_call():
    try:
        run_specialists({"business_name": "Example"}, ["not-a-real-agent"])
    except ValueError as exc:
        assert "Unknown agent IDs" in str(exc)
    else:
        raise AssertionError("Unknown agent must be rejected")


def test_runtime_requires_at_least_one_agent_before_provider_call():
    try:
        run_specialists({"business_name": "Example"}, [])
    except ValueError as exc:
        assert "at least one" in str(exc)
    else:
        raise AssertionError("Empty agent list must be rejected")
