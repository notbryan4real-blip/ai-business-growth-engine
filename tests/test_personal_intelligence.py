from datetime import datetime, timedelta, timezone
from brain.personal_intelligence import Activity, PersonalIntelligence


def test_opt_in_required():
    p = PersonalIntelligence()
    e = Activity("design", datetime.now(timezone.utc), consented=True)
    assert not p.observe(e)
    p.enabled = True
    assert not p.observe(Activity("design", e.occurred_at))
    assert p.observe(e)


def test_prediction_requires_evidence():
    p = PersonalIntelligence(enabled=True)
    now = datetime.now(timezone.utc)
    assert p.predict(now) is None
    for i in range(6):
        p.observe(Activity("design" if i < 5 else "sales", now - timedelta(minutes=i), consented=True))
    result = p.predict(now)
    assert result.category == "design"
    assert 0 < result.confidence < 1


def test_delete_all_personal_data():
    p = PersonalIntelligence(enabled=True)
    p.observe(Activity("design", datetime.now(timezone.utc), consented=True))
    p.record_feedback("design", True)
    p.disable(erase=True)
    assert not p.enabled and not p.events and not p.feedback
