import copy
import json
import threading
import time
from datetime import timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from reactor import feeds
from reactor.models import Evidence, Replay, RunRequest, Settings, iso, now
from reactor.paper import initial, step
from reactor.replay import run_replay
from reactor.service import Reactor, digest, router
from reactor.strategies import evaluate, grade


def evidence(kind="revenue", at=None, **changes):
    at = at or now()-timedelta(minutes=1)
    metrics = {"revenue": {"recent_7d_usd": 180, "previous_7d_usd": 100},
               "unlock": {"unlock_pct_float": 4, "unlock_to_daily_volume": 2},
               "listing": {"stage": "announced"}, "regulation": {}, "miner": {"outflow_multiple": 3}}[kind]
    data = {"reference": kind+"-test", "kind": kind, "asset": "AAVE", "source_url": "https://www.coinbase.com/blog/test",
            "published_at": at-timedelta(minutes=10), "observed_at": at, "event_at": at-timedelta(hours=1),
            "metrics": metrics, "confirmed": True}
    if kind == "regulation":
        data.update(source_url="https://www.sec.gov/news/test", headline="SEC approves crypto asset application")
    data.update(changes)
    return Evidence(**data)


def records(at=None):
    return [evidence(k, at).model_dump(mode="json") for k in ("revenue", "listing")]


def quote(price=100, at=None):
    return {"AAVE": {"asset": "AAVE", "bid": price, "ask": price, "price": price, "quote_at": iso(at), "spread_bps": 0, "volume_24h": 100000}}


class Hub:
    def snapshot(self):
        return {"quotes": quote(), "events": records(), "sources": {"fixture": {"status": "test_fixture"}}, "fetched_at": iso()}


@pytest.fixture
def reactor(tmp_path):
    return Reactor(tmp_path/"reactor.sqlite3", Hub())


def wait(reactor, run_id):
    deadline = time.monotonic()+4
    while time.monotonic() < deadline:
        r = reactor.run(run_id)
        if r["status"] not in {"queued", "running"}:
            return r
        time.sleep(.01)
    raise AssertionError("Reactor run did not finish")


def test_one_signal_cannot_open_position_and_duplicate_articles_cannot_stack():
    one = evidence().model_dump(mode="json")
    assert evaluate([one])["decisions"][0]["action"] == "watch"
    duplicate = {**one, "reference": "different-article"}
    assert evaluate([one, duplicate])["decisions"][0]["supporting_strategies"] == 1
    assert evaluate(records())["decisions"][0]["action"] == "paper_candidate"


def test_negative_unlock_vetoes_positive_hype():
    out = evaluate(records()+[evidence("unlock").model_dump(mode="json")])["decisions"][0]
    assert out["veto"] and out["action"] == "avoid"


def test_zero_baseline_stale_and_unconfirmed_evidence_abstain():
    assert grade(evidence(metrics={"recent_7d_usd": 100, "previous_7d_usd": 0}).model_dump(mode="json"))["status"] == "abstain"
    assert grade(evidence(at=now()-timedelta(days=5)).model_dump(mode="json"))["status"] == "stale"
    assert grade(evidence(confirmed=False).model_dump(mode="json"))["status"] == "abstain"


def test_availability_and_measurement_time_cannot_be_backfilled():
    timestamp = now()-timedelta(minutes=1)
    e = evidence(at=timestamp).model_dump(mode="json")
    assert grade(e, timestamp-timedelta(seconds=1))["score"] == 0
    e["received_at"] = iso(timestamp+timedelta(seconds=30))
    assert grade(e, timestamp)["score"] == 0
    stale = evidence(event_at=now()-timedelta(days=4)).model_dump(mode="json")
    assert grade(stale)["status"] == "stale"


@pytest.mark.parametrize("headline", ["SEC does not approve a crypto ETF", "SEC may approve crypto rules", "SEC proposes new crypto rules", "SEC approves crypto deal and charges issuer with fraud"])
def test_headline_nlp_abstains_on_negation_uncertainty_and_conflict(headline):
    assert grade(evidence("regulation", headline=headline).model_dump(mode="json"))["score"] == 0


def test_spoofed_official_source_is_not_trusted():
    row = evidence("listing", source_url="https://coinbase.com.attacker.invalid/blog/test")
    assert grade(row.model_dump(mode="json"))["status"] == "abstain"


@pytest.mark.parametrize("changes", [
    {"metrics": {"recent_7d_usd": float("nan"), "previous_7d_usd": 100}},
    {"metrics": {"recent_7d_usd": float("inf"), "previous_7d_usd": 100}},
    {"source_url": "https://user:password@example.com"},
    {"source_url": "http://example.com"},
    {"source_url": "https://example.com?api_key=secret"},
    {"published_at": now()+timedelta(days=1)},
    {"observed_at": now().replace(tzinfo=None)},
    {"metrics": {"recent_7d_usd": -1, "previous_7d_usd": 100}},
])
def test_invalid_evidence_rejected(changes):
    with pytest.raises(ValidationError):
        evidence(**changes)


def test_paper_round_trip_charges_both_fees_and_reconciles_pnl():
    cfg = Settings().model_dump(); book = initial(300); at = now()
    decisions = evaluate(records())["decisions"]
    result = step(book, decisions, quote(100, at), cfg, "one", at)
    assert len(result["trades"]) == 1
    assert book["positions"]["AAVE"]["cost_basis"] <= 30
    step(book, [], quote(100, at+timedelta(minutes=1)), cfg, "two", at+timedelta(minutes=1))
    assert not book["positions"] and book["equity"] < 300
    assert book["fees_paid"] == pytest.approx(sum(t["fee"] for t in book["trades"]))
    assert book["equity"]-300 == pytest.approx(book["realized_pnl"])
    assert book["trades"][-1]["pnl"] == pytest.approx(book["realized_pnl"])


def test_stale_or_missing_quotes_block_entries_and_never_fabricate_exits():
    cfg=Settings().model_dump(); book=initial(300); at=now(); decisions=evaluate(records())["decisions"]
    assert not step(book, decisions, quote(at=at-timedelta(minutes=6)), cfg, "stale", at)["trades"]
    step(book, decisions, quote(at=at), cfg, "entry", at)
    out=step(book, [], {}, cfg, "missing", at+timedelta(minutes=2))
    assert not out["trades"] and out["stale_positions"] == ["AAVE"]
    assert "AAVE" in book["positions"]


def test_pause_blocks_entries_but_risk_exits_continue():
    cfg=Settings().model_dump(); book=initial(300); at=now(); decisions=evaluate(records())["decisions"]
    cfg["paused"]=True
    assert not step(book, decisions, quote(at=at), cfg, "paused", at)["trades"]
    cfg["paused"]=False
    step(book, decisions, quote(at=at), cfg, "entry", at)
    cfg["paused"]=True
    out=step(book, decisions, quote(90, at), cfg, "exit", at)
    assert out["trades"][0]["side"] == "sell" and not book["positions"]


def test_daily_circuit_breaker_is_latched_and_gaps_are_not_filled_at_old_stop():
    cfg=Settings().model_dump(); book=initial(300); at=now(); decisions=evaluate(records())["decisions"]
    step(book, decisions, quote(at=at), cfg, "entry", at)
    out=step(book, decisions, quote(50, at), cfg, "gap", at)
    assert out["halted"] and book["halted"]
    assert out["trades"][0]["price"] < 51
    assert not step(book, decisions, quote(at=at), cfg, "retry", at)["trades"]


def test_eight_recorded_handoffs_are_hashed_idempotent_and_persisted(reactor):
    request=RunRequest(request_id="same-research-request")
    run=wait(reactor, reactor.start(request)["id"])
    assert run["status"] == "completed", run
    assert len(run["messages"]) == 8 and run["board"]["model_calls"] == 0
    assert len(run["paper_result"]["trades"]) == 1
    previous="0"*64
    for message in run["messages"]:
        assert message["previous_hash"] == previous
        assert digest({k:v for k,v in message.items() if k!="hash"}) == message["hash"]
        previous=message["hash"]
    assert reactor.start(request)["id"] == run["id"]
    assert len(Reactor(reactor.path, Hub()).overview()["paper"]["trades"]) == 1
    with pytest.raises(HTTPException):
        reactor.start(request.model_copy(update={"paper_execute":False}))


def test_evidence_conflicts_are_atomic_and_import_never_impersonates_provider(reactor):
    reactor.ingest([evidence()])
    assert reactor.overview()["events"][0]["provenance"] == "owner_attested"
    with pytest.raises(HTTPException):
        reactor.ingest([evidence("listing"),evidence(metrics={"recent_7d_usd":900,"previous_7d_usd":100})])
    assert reactor.overview()["event_count"] == 1


def test_no_ai_key_has_a_working_rules_path(reactor, monkeypatch):
    monkeypatch.delenv("AI_API_KEY",raising=False);monkeypatch.delenv("ANTHROPIC_API_KEY",raising=False)
    with pytest.raises(HTTPException) as exc:
        reactor.start(RunRequest(request_id="ai-not-configured",board="ai"))
    assert exc.value.status_code == 503
    assert wait(reactor,reactor.start(RunRequest(request_id="rules-still-work"))["id"])["status"] == "completed"


def test_provider_failure_blocks_entries_and_is_not_automatically_retried(reactor, monkeypatch):
    monkeypatch.setenv("AI_API_KEY","test-not-real")
    def fail(*args,**kw):
        raise RuntimeError("provider unavailable")
    monkeypatch.setattr("httpx.Client.post",fail)
    request=RunRequest(request_id="failed-board-request",board="ai")
    run=wait(reactor,reactor.start(request)["id"])
    assert run["board"]["status"] == "failed" and run["board"]["model_calls"] == 1
    assert run["paper_result"]["trades"] == [] and run["assessment"]
    assert reactor.start(request)["id"] == run["id"]
    assert reactor.overview()["board_calls_reserved_today"] == 1


def test_full_ai_ring_calls_eight_workers_then_one_board_with_real_handoffs(reactor, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-not-real")
    reactor.settings(Settings(daily_board_call_limit=9))
    calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'content':[{'type':'text','text':json.dumps({'summary':'Test provider reviewed supplied evidence','risks':[],'decision':'allow'})}], 'usage':{'input_tokens':12,'output_tokens':8}}
    def model(*a, **kw):
        calls.append(kw['json'])
        return Response()
    monkeypatch.setattr('httpx.Client.post',model)
    run=wait(reactor,reactor.start(RunRequest(request_id='full-ai-ring-test',board='full_ai'))['id'])
    assert run['status']=='completed' and len(calls)==9
    assert run['worker_model_calls']==8 and run['board']['model_calls']==1
    assert all(m['model_review']['status']=='completed' for m in run['messages'])
    assert calls[-1]['model']=='claude-opus-5-5'
    assert 'prior_handoffs' in calls[1]['messages'][0]['content']
    with pytest.raises(HTTPException):
        reactor.start(RunRequest(request_id='budget-exhausted',board='ai'))


def test_full_ai_failure_short_circuits_paid_calls_and_retains_rules(reactor, monkeypatch):
    monkeypatch.setenv('AI_API_KEY','test-not-real')
    reactor.settings(Settings(daily_board_call_limit=9))
    calls=[]
    def fail(*a,**kw):
        calls.append(1)
        raise RuntimeError('Provider failure')
    monkeypatch.setattr('httpx.Client.post',fail)
    run=wait(reactor,reactor.start(RunRequest(request_id='failed-full-ai-ring',board='full_ai'))['id'])
    assert run['status']=='completed' and len(calls)==1
    assert run['board']['status']=='skipped'
    assert not run['paper_result']['trades'] and len(run['messages'])==8


def test_restart_never_replays_work_and_research_only_does_not_trade(reactor):
    run=wait(reactor,reactor.start(RunRequest(request_id="research-only-run",paper_execute=False))["id"])
    assert not reactor.overview()["paper"]["trades"]
    reactor.update(run["id"],lambda r,s:r.update(status="running"))
    reactor.recover()
    assert reactor.run(run["id"])["status"] == "interrupted"
    assert not reactor.overview()["paper"]["trades"]


def test_private_routes_require_auth_and_public_routes_do_not_expose_positions(reactor):
    def auth(token):
        if token!="Bearer test":raise HTTPException(401,"Private")
    app=FastAPI();app.include_router(router(reactor,auth));client=TestClient(app)
    assert client.get('/api/reactor/overview').status_code == 401
    assert client.post('/api/reactor/runs',json={'request_id':'private-run'}).status_code == 401
    assert client.get('/api/reactor/status').json()['live_order_capability'] is False
    assert 'paper' not in client.get('/api/reactor/market').json()
    response=client.post('/api/reactor/runs',headers={'Authorization':'Bearer test'},json={'request_id':'authenticated-run'})
    assert response.status_code == 202
    assert wait(reactor,response.json()['id'])['status'] == 'completed'


def test_revenue_adapter_uses_completed_consecutive_days_and_prior_week(monkeypatch):
    today=now().replace(hour=0,minute=0,second=0,microsecond=0)
    rows=[[int((today-timedelta(days=i)).timestamp()),10 if i<=7 else 5] for i in range(1,15)]
    rows.append([int(today.timestamp()),99999])
    monkeypatch.setattr(feeds,'fetch',lambda *a,**k:{'totalDataChart':rows})
    e=feeds.revenue('AAVE','aave')
    assert e['metrics']=={'recent_7d_usd':70,'previous_7d_usd':35}
    rows.pop(3)
    with pytest.raises(ValueError):feeds.revenue('AAVE','aave')


def test_first_catalog_read_is_a_baseline_not_fake_listings(monkeypatch):
    rows=[{'id':'BTC-USD','quote_currency':'USD','status':'online'}]
    monkeypatch.setattr(feeds,'fetch',lambda *a,**k:rows)
    hub=feeds.FeedHub();assert hub.listings()==[]
    rows.append({'id':'AAVE-USD','quote_currency':'USD','status':'online'})
    events=hub.listings();assert len(events)==1
    assert grade(events[0])['score']==0


def dataset():
    start=now()-timedelta(hours=10)
    candles=[]
    for i in range(50):
        candles.append({'open_at':start+timedelta(minutes=i*10),'close_at':start+timedelta(minutes=(i+1)*10),
                        'open':100,'high':101,'low':99,'close':100})
    return {'asset':'AAVE','candles':candles,'events':[evidence(k,at=start-timedelta(minutes=1)) for k in ('revenue','listing')]}


def test_replay_future_events_never_trade_and_holdout_has_independent_capital():
    data=dataset();out=run_replay(Replay(**data))
    assert out['holdout']['starting_cash']==out['full_period']['starting_cash']==300
    assert out['holdout']['closed_trades']>0
    assert out['holdout']['net_pnl']<0 # Flat prices lose both fees and slippage.
    data['events']=[evidence(k) for k in ('revenue','listing')]
    out=run_replay(Replay(**data))
    assert out['full_period']['closed_trades']==0
    assert out['full_period']['net_pnl']==0


def test_intrabar_stop_wins_over_target():
    data=dataset();data['candles'][1].update(high=110,low=90)
    out=run_replay(Replay(**data))
    first_sell=next(t for t in out['full_period']['trades'] if t['side']=='sell')
    assert first_sell['reason']=='intrabar_stop' and first_sell['pnl']<0


def test_replay_rejects_unsorted_or_incomplete_candles():
    data=dataset();data['candles'][2]['open_at']=data['candles'][0]['open_at']
    with pytest.raises(ValidationError):Replay(**data)


def test_paper_reviews_reach_council_without_becoming_business_revenue(tmp_path):
    from brain.council import Brain, Observation, Meeting
    b=Brain(tmp_path/'brain.sqlite3')
    b.ingest(Observation(source='crypto',reference='paper-review',observed_at=now(),summary='Paper research completed.',details={'mode':'paper_only','real_revenue':False}))
    result=b.start(Meeting(request_id='council-crypto-test'))
    full=b.meeting(result['id'])
    assert 'finance' in full['participants']
    assert any('not business revenue' in t['details'] for t in b.overview()['tasks'])
