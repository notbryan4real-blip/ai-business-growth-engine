from datetime import timedelta
import json
import time

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from agents import runtime
from brain.council import Brain, Meeting, MeetingPreview, Memory, Observation, now, router
from brain.insights import run_metrics, select_memory


@pytest.fixture
def brain(tmp_path):
    instance = Brain(tmp_path / 'brain.sqlite3')
    yield instance
    instance.worker.shutdown(wait=True)


def remember(brain, text, kind='fact', **kwargs):
    return brain.remember(Memory(kind=kind, text=text, source='Owner checked', **kwargs))


def observe(brain, source):
    return brain.ingest(Observation(source=source, reference='observed-' + source,
                                   observed_at=now(), summary='Supplied observation'))


def test_retrieval_finds_older_relevant_memory_and_due_commitments(brain):
    relevant = remember(brain, 'Print shop customer artwork must be approved before printing', 'procedure')
    due = remember(brain, 'Deliver the promised proof', 'commitment', due_at=now()+timedelta(hours=2))
    preference = remember(brain, 'Work from an Android phone only', 'preference')
    for index in range(40):
        remember(brain, 'Unrelated archive item ' + str(index))
    records = brain.overview()['memory']
    selected = select_memory(records, 'Review print shop artwork', now())
    assert selected[0]['id'] == due['id']
    assert {relevant['id'], preference['id']} <= {m['id'] for m in selected}
    assert len(selected) == 30
    assert next(m for m in selected if m['id'] == relevant['id']) == relevant
    assert len(records) == 43  # Retrieval does not remove stored memories.


def test_memory_context_is_bounded_without_dropping_provenance(brain):
    for index in range(35):
        remember(brain, str(index) + ' x' * 700)
    selected = select_memory(brain.overview()['memory'], 'A new task', now())
    assert len(json.dumps(selected, ensure_ascii=False)) <= 14000
    assert 0 < len(selected) < 30
    assert all(m['verified_by'] == 'owner' and m['source'] == 'Owner checked' and m['id'] for m in selected)


def test_rules_considers_old_deadlines_beyond_previous_last_thirty_cutoff(brain):
    due = remember(brain, 'Deliver the older commitment', 'commitment', due_at=now()+timedelta(hours=1))
    for index in range(35):
        remember(brain, 'Later note ' + str(index))
    brain.start(Meeting(request_id='old-deadline-rule'))
    assert any(due['id'] in task['evidence_ids'] for task in brain.overview()['tasks'])


def test_preview_does_not_reserve_calls_store_evidence_or_run_models(brain, monkeypatch):
    monkeypatch.setenv('AI_API_KEY', 'test-only')
    monkeypatch.setattr(runtime, '_call_anthropic', lambda *a: pytest.fail('Preview called a model'))
    item = remember(brain, 'Use the checked print shop workflow', 'procedure')
    before = brain.transact(lambda s: s)
    plan = brain.preview(MeetingPreview(agenda='Print shop workflow'))
    assert plan['can_start'] and plan['model_calls_required'] == 3
    assert plan['participants'] == ['personal', 'qa', 'orchestrator']
    assert plan['memory'][0]['id'] == item['id']
    assert plan['cost_usd'] is None and plan['external_execution'] is False
    assert brain.transact(lambda s: s) == before


def test_preview_explains_missing_provider_and_exhausted_budget(brain, monkeypatch):
    monkeypatch.delenv('AI_API_KEY', raising=False)
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    brain.transact(lambda s: s['settings'].update(daily_model_call_limit=0))
    plan = brain.preview(MeetingPreview())
    assert not plan['can_start'] and len(plan['blockers']) == 2
    assert plan['model_calls_remaining'] == 0
    assert brain.preview(MeetingPreview(mode='rules'))['can_start']


def test_start_rejects_a_larger_call_count_than_the_owner_reviewed(brain, monkeypatch):
    monkeypatch.setenv('AI_API_KEY', 'test-only')
    monkeypatch.setattr(runtime, '_call_anthropic', lambda *a: pytest.fail('Unreviewed calls started'))
    plan = brain.preview(MeetingPreview())
    for source in ('gmail', 'instagram', 'business', 'calendar'):
        observe(brain, source)
    with pytest.raises(HTTPException) as error:
        brain.start(Meeting(request_id='changed-run-plan', mode='ai', max_model_calls=plan['model_calls_required']))
    assert error.value.status_code == 409
    assert brain.overview()['model_calls_reserved_today'] == 0
    assert not brain.overview()['meetings']
    assert brain.slot.acquire(blocking=False)
    brain.slot.release()


def test_retrieved_memory_reaches_the_provider_and_is_recorded(brain, monkeypatch):
    monkeypatch.setenv('AI_API_KEY', 'test-only')
    lesson = remember(brain, 'Confirm artwork proofs before any print shop delivery', 'procedure')
    for index in range(35):
        remember(brain, 'Unrelated record ' + str(index))
    sent = []
    def provider(agent, evidence, prior):
        sent.append(evidence)
        return {'summary': 'Review complete', 'findings': [], 'risks': [], 'next_actions': ['Review the proof'],
                'evidence_gaps': [], 'confidence': 'low'}, 'test-model'
    monkeypatch.setattr(runtime, '_call_anthropic', provider)
    request = Meeting(request_id='retrieved-context-run', mode='ai', agenda='Print shop artwork delivery', max_model_calls=3)
    mid = brain.start(request)['id']
    deadline = time.monotonic()+3
    while brain.meeting(mid)['status'] in {'queued', 'running'} and time.monotonic() < deadline:
        time.sleep(.01)
    meeting = brain.meeting(mid)
    assert meeting['status'] == 'completed'
    assert lesson['id'] in meeting['context_summary']['memory_ids']
    assert lesson['id'] in {m['id'] for m in sent[0]['owner_memory']}
    assert meeting['memory_selection']['omitted_count'] == 6
    assert brain.start(request)['id'] == mid and len(sent) == 3
    assert len(brain.overview()['memory']) == 36  # No automatic learning from model claims.


def test_legacy_request_ids_still_deduplicate_without_the_optional_call_cap(brain):
    request = Meeting(request_id='legacy-request-id', mode='rules', agenda='Review current priorities')
    mid = brain.start(request)['id']
    brain.update_meeting(mid, lambda m, s: m.update(request={
        'request_id': request.request_id, 'mode': request.mode, 'agenda': request.agenda}))
    assert brain.start(request)['id'] == mid


def test_metrics_separate_modes_and_do_not_invent_missing_measurements():
    at = now()
    rows = [
        {'mode': 'rules', 'status': 'completed', 'model_calls': 0},
        {'mode': 'ai', 'status': 'completed', 'model_calls': 3, 'created_at': at.isoformat(),
         'completed_at': (at+timedelta(seconds=9)).isoformat()},
        {'mode': 'ai', 'status': 'completed', 'model_calls': 3},  # Unknown timing.
        {'mode': 'ai', 'status': 'failed', 'model_calls': 2},
        {'mode': 'ai', 'status': 'cancelled', 'model_calls': 1},
        {'mode': 'ai', 'status': 'running', 'model_calls': 1},
    ]
    result = run_metrics(rows)
    ai = result['by_mode']['ai']
    assert ai['completion_rate'] == 50 and ai['terminal'] == 4 and ai['total'] == 5
    assert ai['model_calls_attempted'] == 10
    assert ai['mean_completed_seconds'] == 9 and ai['timed_completed_runs'] == 1
    assert result['provider_cost_usd'] is None and result['tool_call_accuracy'] is None
    empty = run_metrics([])['by_mode']['ai']
    assert empty['completion_rate'] is None and empty['mean_completed_seconds'] is None


def test_private_preview_includes_portfolio_without_importing_it(brain, monkeypatch):
    from app import require_api_token
    monkeypatch.setenv('APP_API_TOKEN', 'test-owner')
    monkeypatch.setenv('AI_API_KEY', 'test-provider')
    api = FastAPI()
    api.include_router(router(brain, require_api_token, lambda: {'tasks': [], 'money': {}}))
    client = TestClient(api)
    before = brain.transact(lambda s: s)
    assert client.post('/api/brain/meetings/preview', json={}).status_code == 401
    response = client.post('/api/brain/meetings/preview', json={'agenda': 'Review business priorities'},
                           headers={'Authorization': 'Bearer test-owner'})
    assert response.status_code == 200
    assert response.json()['participants'] == ['project', 'qa', 'orchestrator']
    assert 'business' in response.json()['fresh_sources']
    assert brain.transact(lambda s: s) == before
    assert client.post('/api/brain/meetings/preview', json={'agenda': 'x'},
                       headers={'Authorization': 'Bearer test-owner'}).status_code == 422


def test_health_and_review_queue_keep_pending_decisions_older_than_recent_sixty(brain):
    brain.transact(lambda s: s['decisions'].extend([{'id': str(i), 'status': 'proposed'} for i in range(80)]))
    overview = brain.overview()
    assert len(overview['decisions']) == 80
    assert overview['performance']['pending_owner_decisions'] == 80
