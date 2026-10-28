'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { runInNewContext } = require('node:vm');
const source = readFileSync(join(__dirname, '../dashboard/jarvis-voice.js'), 'utf8');

class Element extends EventTarget {
  constructor() { super(); this.textContent = ''; this.value = ''; this.disabled = false; this.attributes = {}; }
  setAttribute(name, value) { this.attributes[name] = value; }
  click() { if (!this.disabled) this.onclick?.(); }
}
function setup({ voices = [], synthesis = true, utterance = true, recognition = true } = {}) {
  const elements = Object.fromEntries(['voiceStatus', 'voiceChoice', 'voiceSpeak', 'voiceListen', 'voiceStop', 'voiceRun',
    'voiceText', 'agenda', 'meetingSummary', 'briefing', 'review', 'rules', 'council'].map(id => [id, new Element()]));
  elements.meetingSummary.textContent = 'Select a meeting to see its actual reports and handoffs.';
  elements.briefing.textContent = 'Your next task is to review the artwork proof.';
  let rulesRuns = 0, agendaChanges = 0;
  elements.rules.onclick = () => rulesRuns++;
  elements.agenda.addEventListener('input', () => agendaChanges++);
  const synth = new EventTarget();
  Object.assign(synth, { voices, spoken: [], cancelCalls: 0, speaking: false });
  synth.getVoices = () => synth.voices;
  synth.speak = item => synth.spoken.push(item);
  synth.cancel = () => synth.cancelCalls++;
  const recognizers = [];
  class Recognition {
    constructor() { recognizers.push(this); }
    start() { this.started = true; }
    abort() { this.aborted = true; this.onend?.(); }
  }
  const window = {
    speechSynthesis: synthesis ? synth : undefined,
    SpeechSynthesisUtterance: utterance ? class { constructor(text) { this.text = text; } } : undefined,
    SpeechRecognition: recognition ? Recognition : undefined,
  };
  runInNewContext(source, { window, Event, document: {
    getElementById: id => elements[id], querySelector: () => elements.council,
  } });
  return { elements, synth, window, recognizers, get utter() { return synth.spoken.at(-1); },
    get rulesRuns() { return rulesRuns; }, get agendaChanges() { return agendaChanges; } };
}
const voice = (name, lang, isDefault = false) => ({ name, lang, default: isDefault });
const female = voice('Google UK English Female', 'en-GB');
const george = voice('Microsoft George', 'en-GB', true);
const american = voice('English US', 'en-US', true);
const french = voice('French', 'fr-FR', true);

test('chooses by language/default without the Female substring regression', () => {
  const cases = [
    [[female, george], george], [[american, female], female],
    [[voice('Daniel', 'fr-FR'), female], female],
    [[french, voice('Other English', 'en-AU'), american], american],
    [[french], null], [[], null],
  ];
  for (const [voices, expected] of cases) {
    const app = setup({ voices }); app.elements.voiceListen.click();
    assert.equal(app.utter.voice, expected);
    assert.equal(app.utter.lang, expected?.lang.toLowerCase() || 'en-GB');
  }
});
test('normalizes British language tags', () => {
  for (const lang of ['EN-gb', 'en_GB', 'en-GB-x-test']) {
    const british = voice('Installed voice', lang);
    const app = setup({ voices: [american, british] }); app.elements.voiceListen.click();
    assert.equal(app.utter.voice, british);
    assert.equal(app.utter.lang, lang.toLowerCase().replace(/_/g, '-'));
  }
});
test('explains English and browser-default fallbacks', () => {
  assert.match(setup({ voices: [american] }).elements.voiceChoice.textContent, /No British English voice listed; using English US/);
  for (const voices of [[], [french]]) {
    const app = setup({ voices }); app.elements.voiceListen.click();
    assert.equal(app.utter.voice, null);
    assert.match(app.elements.voiceChoice.textContent, /browser default requested.*not guaranteed/);
  }
});
test('late voices update feedback but never autoplay', () => {
  const app = setup(); app.synth.voices = [george];
  app.synth.dispatchEvent(new Event('voiceschanged'));
  assert.match(app.elements.voiceChoice.textContent, /Microsoft George/);
  assert.equal(app.synth.spoken.length, 0);
  app.elements.voiceListen.click(); assert.equal(app.utter.voice, george);
});
test('rechecks voices on tap even without a voiceschanged event', () => {
  const app = setup(); app.synth.voices = [george]; app.elements.voiceListen.click();
  assert.equal(app.utter.voice, george);
  app.utter.onend(); app.synth.voices = []; app.elements.voiceListen.click();
  assert.equal(app.utter.voice, null);
});
test('voice changes cannot overwrite the currently playing voice', () => {
  const app = setup({ voices: [american] }); app.elements.voiceListen.click();
  const label = app.elements.voiceChoice.textContent;
  app.synth.voices = [george]; app.synth.dispatchEvent(new Event('voiceschanged'));
  assert.equal(app.elements.voiceChoice.textContent, label);
  assert.equal(app.utter.voice, american);
});
test('unsupported speech APIs are explained and controls disabled', () => {
  for (const options of [{ synthesis: false }, { utterance: false }]) {
    const app = setup(options); assert.ok(app.elements.voiceListen.disabled);
    assert.match(app.elements.voiceChoice.textContent, /unavailable/);
  }
  const app = setup({ recognition: false });
  assert.ok(app.elements.voiceSpeak.disabled);
  assert.match(app.elements.voiceStatus.textContent, /Type your agenda/);
});
test('starting, reading and finishing update feedback and accessible actions', () => {
  const app = setup(); app.elements.voiceListen.click();
  assert.match(app.elements.voiceStatus.textContent, /Starting/);
  assert.equal(app.elements.voiceListen.attributes['aria-label'], 'Stop reading JARVIS briefing');
  assert.equal(app.elements.voiceStop.disabled, false);
  app.utter.onstart(); assert.match(app.elements.voiceStatus.textContent, /Reading/);
  app.utter.onend(); assert.match(app.elements.voiceStatus.textContent, /finished/);
  assert.equal(app.elements.voiceListen.textContent, 'Read briefing');
  assert.equal(app.elements.voiceStop.disabled, true);
});
test('queued stop and late events cannot affect a later readout', () => {
  const app = setup(); app.elements.voiceListen.click(); const old = app.utter;
  app.elements.voiceListen.click();
  assert.equal(app.synth.spoken.length, 1); assert.equal(app.synth.cancelCalls, 1);
  app.elements.voiceListen.click(); const before = app.elements.voiceStatus.textContent;
  old.onstart(); old.onend(); old.onerror({ error: 'canceled' });
  assert.equal(app.elements.voiceStatus.textContent, before);
  assert.equal(app.elements.voiceListen.textContent, 'Stop reading');
});
test('playback errors and synchronous startup failures leave a retryable control', () => {
  for (const error of ['canceled', 'interrupted', 'voice-unavailable', 'not-allowed']) {
    const app = setup(); app.elements.voiceListen.click(); app.utter.onerror({ error });
    assert.match(app.elements.voiceStatus.textContent, ['canceled', 'interrupted'].includes(error) ? /stopped/ : /could not play/);
    app.elements.voiceListen.click(); assert.equal(app.synth.spoken.length, 2);
  }
  const app = setup(); app.synth.speak = () => { throw Error('unavailable'); };
  app.elements.voiceListen.click();
  assert.equal(app.elements.voiceListen.textContent, 'Read briefing');
  assert.match(app.elements.voiceStatus.textContent, /could not start/);
});
test('reads a selected meeting or the latest briefing, bounded to 4000 characters', () => {
  const app = setup(); app.elements.meetingSummary.textContent = '  ' + 'x'.repeat(4100) + '  ';
  app.elements.voiceListen.click(); assert.equal(app.utter.text, 'JARVIS briefing. ' + 'x'.repeat(4000));
  const empty = setup(); empty.elements.briefing.textContent = 'Your briefing will bring together current evidence.';
  empty.elements.voiceListen.click(); assert.equal(empty.synth.spoken.length, 0);
});
test('dictation fills bounded agenda text and invalidates the preview without running anything', () => {
  const app = setup(); app.elements.voiceSpeak.click();
  app.recognizers[0].onresult({ results: [[{ transcript: 'x'.repeat(2100) }]] });
  assert.equal(app.elements.agenda.value.length, 2000);
  assert.equal(app.agendaChanges, 1); assert.equal(app.rulesRuns, 0);
  assert.equal(app.synth.spoken.length, 0);
  app.elements.voiceRun.click(); assert.equal(app.rulesRuns, 1);
});
test('Stop discards late transcripts and late end events from a previous recognizer', () => {
  const app = setup(); app.elements.voiceSpeak.click(); const old = app.recognizers[0];
  app.elements.voiceStop.click(); app.elements.voiceSpeak.click();
  old.onresult({ results: [[{ transcript: 'Stale input' }]] }); old.onend();
  assert.equal(app.elements.agenda.value, '');
  assert.equal(app.elements.voiceSpeak.textContent, 'Stop dictation');
  assert.equal(old.aborted, true);
});
test('microphone errors restore controls and typed rules mode still requires connection', () => {
  const app = setup(); app.elements.voiceSpeak.click(); app.recognizers[0].onerror({ error: 'not-allowed' });
  assert.equal(app.elements.voiceSpeak.textContent, 'Dictate agenda');
  assert.match(app.elements.voiceStatus.textContent, /microphone permission/);
  app.elements.review.disabled = true; app.elements.voiceRun.click();
  assert.equal(app.rulesRuns, 0); assert.match(app.elements.voiceStatus.textContent, /Connect/);
});
test('starting dictation stops readout and starting readout aborts dictation', () => {
  const app = setup(); app.elements.voiceListen.click(); app.elements.voiceSpeak.click();
  assert.equal(app.synth.cancelCalls, 1);
  app.elements.voiceListen.click(); assert.ok(app.recognizers[0].aborted);
  assert.equal(app.synth.spoken.length, 2);
});
