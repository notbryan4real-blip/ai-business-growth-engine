'use strict';
var missionConnected;
(() => {
  const node = id => document.getElementById(id);
  let connected = false, working = false, selected = null, selection = 0, listVersion = 0;
  let timer = null, creation = null, renderedId = null, previousStatus = null;
  const labels = {awaiting_start:'Plan ready', starting:'Starting', running:'Council running',
    awaiting_review:'Waiting for your review', interrupted:'Interrupted · review required',
    reviewed:'Review saved', stopping:'Stopping after current call', cancelled:'Stopped'};
  const status = (message, error=false) => {
    node('missionStatus').textContent = message;
    node('missionStatus').classList.toggle('error', error);
  };
  const controls = () => {
    for (const id of ['missionCreate','missionRefreshList','missionGoal','missionMode']) node(id).disabled = !connected || working;
    node('missionStart').disabled = working || !selected?.plan.can_start;
    for (const id of ['missionReplan','missionCancel','missionReview']) node(id).disabled = working;
  };
  async function perform(fn) {
    if (working) return;
    if (!connected) { status('Connect your Swarm above first.', true); return; }
    working = true; controls();
    try { await fn(); } catch (error) { status(error.message, true); }
    finally { working = false; controls(); }
  }
  async function refreshList() {
    const ticket = ++listVersion, response = await request('/missions');
    if (ticket !== listVersion) return;
    const root = node('missionList'); root.replaceChildren();
    for (const mission of response.missions) {
      const button = el('button', mission.goal + '\n' + (labels[mission.status] || mission.status), 'meeting-button');
      button.onclick = () => perform(() => openMission(mission.id));
      root.append(button);
    }
    if (!response.missions.length) root.append(el('p', 'No missions yet. Save a goal above to build its plan.', 'hint'));
    const m = response.metrics;
    node('missionMetrics').textContent = m.total + ' saved missions · ' + m.reviewed + ' reviewed · ' +
      (m.reviewed ? m.owner_rated_useful + ' rated useful by you.' : 'No outcome ratings yet.') + ' These ratings do not measure revenue or tool accuracy.';
    node('missionStorage').textContent = response.storage_notice;
  }
  function renderMission(mission) {
    const changed = renderedId !== mission.id;
    const enteringReview = changed || !['awaiting_review','interrupted'].includes(previousStatus);
    selected = mission; renderedId = mission.id; previousStatus = mission.status;
    node('missionRecord').hidden = false;
    node('missionTitle').textContent = mission.goal;
    node('missionBadge').textContent = labels[mission.status] || mission.status;
    const steps = node('missionSteps'); steps.replaceChildren();
    const ran = Boolean(mission.result), reviewed = Boolean(mission.review);
    for (const text of [
      'Evidence and memory checked · plan saved',
      'Council · ' + (ran ? mission.result.status : 'waiting for your start'),
      'Owner review · ' + (reviewed ? 'saved' : mission.status === 'awaiting_review' ? 'ready for you' : 'pending'),
      'Reviewed lesson · ' + (mission.review?.lesson_id ? 'saved to shared memory' : reviewed ? 'none added' : 'optional after review')
    ]) steps.append(el('li', text));
    const p = mission.plan, plan = node('missionPlan'); plan.replaceChildren();
    plan.append(el('p', mission.mode === 'ai'
      ? p.model_calls_required + ' model calls planned · ' + p.model_calls_remaining + ' available when planned. Provider charges may apply.'
      : 'Rules mode prioritizes stored follow-ups with zero model calls. Choose AI when creating a mission for goal-specific model analysis.'));
    if (mission.mode === 'ai') plan.append(el('p', 'Roles: ' + p.participants.join(' → '), 'hint'));
    plan.append(el('p', 'Fresh: ' + (p.fresh_sources.join(', ') || 'none') + '. Stale: ' + (p.stale_sources.join(', ') || 'none') + '. Missing: ' + (p.missing_sources.join(', ') || 'none') + '.', 'hint'));
    const memory = el('details'); memory.append(el('summary', p.memory.length + ' memories selected · ' + p.memory_omitted + ' omitted'));
    for (const item of p.memory) memory.append(el('p', item.kind + ': ' + item.text + ' · ' + item.source, 'hint'));
    plan.append(memory);
    if (mission.status === 'awaiting_start') {
      plan.append(el('p', 'Starting rechecks the call limit. Saving or opening this plan spends no model calls.', 'hint'));
      for (const blocker of p.blockers) plan.append(el('p', blocker, 'error'));
    }
    if (mission.error) plan.append(el('p', mission.error, 'error'));
    node('missionStart').hidden = node('missionReplan').hidden = mission.status !== 'awaiting_start';
    node('missionStart').textContent = mission.mode === 'ai' ? 'Start reviewed plan · up to ' + p.model_calls_required + ' model calls' : 'Start reviewed plan · free rules';
    node('missionCancel').hidden = ['reviewed','cancelled','stopping'].includes(mission.status);
    const result = node('missionResult'); result.replaceChildren();
    if (mission.result) {
      const r = mission.result;
      result.append(el('h3', 'Execution result'), el('p', r.error || r.summary || 'Reports are still arriving.'),
        el('p', r.model_calls + ' model calls attempted. External actions executed: none.', 'hint'));
      for (const action of r.actions) result.append(el('p', 'Proposed action: ' + action));
      for (const risk of r.risks) result.append(el('p', 'Review point: ' + risk, 'hint'));
      for (const gap of r.evidence_gaps) result.append(el('p', 'Evidence gap: ' + gap, 'hint'));
      if (mission.reports_available) {
        const record = el('button', 'Open council reports', 'secondary');
        record.onclick = () => perform(async () => { await openMeeting(r.meeting_id); tab('council'); });
        result.append(record);
      }
    }
    if (mission.status === 'interrupted') result.append(el('p', 'No calls will replay. Review the partial result as needing revision; create a new mission explicitly for another run.', 'hint'));
    node('missionReviewForm').hidden = !['awaiting_review','interrupted'].includes(mission.status);
    if (enteringReview) { node('missionNote').value = ''; node('missionLesson').value = ''; node('missionOutcome').value = mission.status === 'interrupted' ? 'needs_revision' : 'useful'; }
    node('missionOutcome').disabled = mission.status === 'interrupted';
    if (mission.review) {
      result.append(el('h3', 'Your saved review'), el('p', mission.review.note),
        el('p', mission.review.outcome === 'useful' ? 'You rated this result useful.' : 'You marked this result as needing revision.', 'hint'));
    }
    const events = node('missionEvents'); events.replaceChildren();
    for (const event of mission.events) events.append(el('li', new Date(event.at).toLocaleString() + ' · ' + event.action));
    controls();
  }
  async function openMission(id) {
    const ticket = ++selection; clearTimeout(timer);
    const mission = await request('/missions/' + encodeURIComponent(id));
    if (ticket !== selection) return;
    renderMission(mission);
    if (['starting','running','stopping'].includes(mission.status)) {
      timer = setTimeout(async () => {
        if (document.hidden || node('missions').hidden || selected?.id !== id) return;
        try { await openMission(id); } catch (error) { status('Live updates paused. Tap Refresh missions: ' + error.message, true); }
      }, 2500);
    }
  }
  node('missionForm').onsubmit = event => {
    event.preventDefault();
    return perform(async () => {
      const goal = node('missionGoal').value.trim(), mode = node('missionMode').value;
      if (goal.length < 3) throw Error('Describe your goal in at least three characters.');
      if (!creation || creation.goal !== goal || creation.mode !== mode) creation = {request_id:crypto.randomUUID(), goal, mode};
      const mission = await request('/missions', {method:'POST', body:JSON.stringify(creation)});
      creation = null; ++selection; clearTimeout(timer); renderMission(mission); await refreshList();
      status('Plan saved. Review the context and call count, then choose Start reviewed plan.');
    });
  };
  node('missionStart').onclick = () => perform(async () => {
    if (!selected || selected.status !== 'awaiting_start' || !selected.plan.can_start) throw Error('Open an available plan before starting.');
    const id = selected.id;
    await request('/missions/' + id + '/start', {method:'POST', body:JSON.stringify({plan_id:selected.plan_id, approved_model_calls:selected.plan.model_calls_required})});
    await openMission(id); await refreshList(); await load();
    status(selected?.status === 'awaiting_review' ? 'Council finished. Review its result below.' : 'Mission started. You can return to this saved record.');
  });
  node('missionReplan').onclick = () => perform(async () => {
    if (!selected || selected.status !== 'awaiting_start') return;
    const mission = await request('/missions/' + selected.id + '/refresh', {method:'POST'});
    renderMission(mission); status('Plan refreshed. Review the new evidence and call count.');
  });
  node('missionCancel').onclick = () => perform(async () => {
    if (!selected) return;
    const id = selected.id; await request('/missions/' + id + '/cancel', {method:'POST'});
    await openMission(id); await refreshList(); status('Stop recorded. An in-flight provider call may finish; it will not be replayed.');
  });
  node('missionReviewForm').onsubmit = event => {
    event.preventDefault();
    return perform(async () => {
      if (!selected || !['awaiting_review','interrupted'].includes(selected.status)) return;
      const body = {outcome:node('missionOutcome').value, note:node('missionNote').value.trim(), lesson:node('missionLesson').value.trim()};
      if (body.note.length < 3 || (body.lesson && body.lesson.length < 3)) throw Error('Write a review of at least three characters; leave the lesson blank or write at least three characters.');
      const mission = await request('/missions/' + selected.id + '/review', {method:'POST', body:JSON.stringify(body)});
      renderMission(mission); await refreshList(); await load();
      status(body.lesson ? 'Review and your checked lesson saved. No external action was executed.' : 'Review saved. No lesson or external action was created.');
    });
  };
  node('missionRefreshList').onclick = () => perform(async () => { await refreshList(); if (selected) await openMission(selected.id); status('Saved mission records refreshed.'); });
  node('tab-missions').addEventListener('click', () => { if (connected && selected && !working) perform(() => openMission(selected.id)); });
  missionConnected = () => {
    const first = !connected; connected = true; controls();
    if (first) refreshList().then(() => status('Choose a saved mission or build a new plan.')).catch(error => status(error.message, true));
  };
  if (typeof state !== 'undefined' && state) missionConnected();
})();
