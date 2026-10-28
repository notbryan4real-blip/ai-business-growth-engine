'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { createContext, runInContext } = require('node:vm');
const source = readFileSync(join(__dirname, '../dashboard/jarvis.js'), 'utf8');
const html = readFileSync(join(__dirname, '../dashboard/jarvis.html'), 'utf8');

class Element extends EventTarget {
  constructor() {
    super(); this.value = ''; this.textContent = ''; this.children = [];
    this.hidden = false; this.disabled = false; this.attributes = {};
    this.classList = { toggle() {} };
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  setAttribute(name, value) { this.attributes[name] = value; }
  click() { if (!this.disabled) return this.onclick?.(); }
}
const plan = () => ({ mode: 'ai', agenda: 'Review print shop delivery', model_calls_required: 3,
  model_calls_remaining: 12, participants: ['personal', 'qa', 'orchestrator'], memory: [], memory_omitted: 0,
  fresh_sources: [], stale_sources: [], missing_sources: ['gmail'], can_start: true, blockers: [] });
function setup(preview = plan()) {
  const nodes = Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(match => [match[1], new Element()]));
  const requests = [];
  const context = createContext({
    document: { getElementById: id => nodes[id], createElement: () => new Element(), querySelectorAll: () => [] },
    location: { hostname: 'localhost', origin: 'http://localhost' },
    localStorage: { getItem: () => null }, sessionStorage: { getItem: () => null },
    setTimeout, clearTimeout, Event, crypto: { randomUUID: () => 'test-request-12345' },
    fakeRequest: async (path, options) => {
      requests.push({ path, body: options?.body ? JSON.parse(options.body) : null });
      if (path === '/meetings/preview') return preview;
      if (path === '/meetings') return { id: 'test-meeting' };
      throw Error('Unexpected request: ' + path);
    },
  });
  runInContext(source, context);
  runInContext('request = fakeRequest; state = {hierarchy: []}; load = async () => {}; openMeeting = async () => {}; tab = () => {};', context);
  nodes.agenda.value = preview.agenda;
  return { nodes, requests, context };
}

test('Preview AI council makes no paid run until the reviewed start button is tapped', async () => {
  const app = setup(); await app.nodes.ai.click();
  assert.deepEqual(app.requests.map(r => r.path), ['/meetings/preview']);
  assert.equal(app.nodes.runPreview.hidden, false);
  await app.nodes.confirmAi.click();
  assert.equal(app.requests[1].path, '/meetings');
  assert.equal(app.requests[1].body.max_model_calls, 3);
  assert.equal(app.requests[1].body.agenda, 'Review print shop delivery');
  assert.equal(app.nodes.runPreview.hidden, true);
});
test('editing an agenda invalidates its earlier preview', async () => {
  const app = setup(); await app.nodes.ai.click();
  app.nodes.agenda.value = 'A different task'; app.nodes.agenda.dispatchEvent(new Event('input'));
  await app.nodes.confirmAi.click();
  assert.equal(app.requests.length, 1);
  assert.match(app.nodes.status.textContent, /Preview the run again/);
});
test('programmatic agenda changes cannot reuse the previous approval', async () => {
  const app = setup(); await app.nodes.ai.click();
  app.nodes.agenda.value = 'Changed by another control'; await app.nodes.confirmAi.click();
  assert.equal(app.requests.length, 1);
});
test('an agenda edited during a pending preview does not display a stale plan', async () => {
  const app = setup(); let release;
  app.context.fakeRequest = () => new Promise(resolve => { release = () => resolve(plan()); });
  runInContext('request = fakeRequest;', app.context);
  const pending = app.nodes.ai.click(); app.nodes.agenda.value = 'New agenda while waiting';
  release(); await pending;
  assert.equal(app.nodes.runPreview.hidden, true);
  assert.match(app.nodes.status.textContent, /Agenda changed/);
});
test('blocked previews disable paid start, and cancel discards a valid preview', async () => {
  const blocked = setup({ ...plan(), can_start: false, blockers: ['No call allowance remaining.'] });
  await blocked.nodes.ai.click(); await blocked.nodes.confirmAi.click();
  assert.equal(blocked.nodes.confirmAi.disabled, true); assert.equal(blocked.requests.length, 1);
  const app = setup(); await app.nodes.ai.click(); app.nodes.cancelPreview.click();
  await app.nodes.confirmAi.click(); assert.equal(app.requests.length, 1);
});
test('rapid repeated confirmation creates only one run while the request is pending', async () => {
  const app = setup(); await app.nodes.ai.click();
  let release;
  app.context.fakeRequest = (path, options) => {
    app.requests.push({ path, body: JSON.parse(options.body) });
    return new Promise(resolve => { release = () => resolve({ id: 'single-run' }); });
  };
  runInContext('request = fakeRequest;', app.context);
  const first = app.nodes.confirmAi.click(); await app.nodes.confirmAi.click();
  assert.equal(app.requests.filter(r => r.path === '/meetings').length, 1);
  release(); await first;
});
test('saved-memory search filters records and explains an empty match', () => {
  const app = setup(); app.context.saved = [{kind:'procedure', text:'Check print artwork', source:'Owner checked'}];
  runInContext('state.memory = saved;', app.context);
  app.nodes.memorySearch.value = 'artwork'; app.nodes.memorySearch.dispatchEvent(new Event('input'));
  assert.equal(app.nodes.memories.children.length, 1);
  app.nodes.memorySearch.value = 'unmatched'; app.nodes.memorySearch.dispatchEvent(new Event('input'));
  assert.equal(app.nodes.memories.children[0].textContent, 'No matching saved memories.');
});
