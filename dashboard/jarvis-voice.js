/* Browser agenda dictation and briefing readout, not conversational AI control. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const status = message => { $('voiceStatus').textContent = message; };
  const synth = window.speechSynthesis;
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const canRead = Boolean(synth && typeof window.SpeechSynthesisUtterance === 'function');
  let recognizer = null;
  let active = null;

  const language = voice => voice.lang.toLowerCase().replace(/_/g, '-');
  const british = voice => /^en-gb(?:-|$)/.test(language(voice));
  function chooseVoice() {
    const voices = synth.getVoices();
    const gb = voices.filter(british);
    const english = voices.filter(voice => /^en(?:-|$)/.test(language(voice)));
    // Names do not reliably identify gender or identity.
    return gb.find(voice => voice.default) || gb[0] ||
      english.find(voice => voice.default) || english[0] || null;
  }
  function describeVoice(voice) {
    if (!voice) return 'No English voice listed; browser default requested. British English is not guaranteed.';
    const label = voice.name + ' (' + voice.lang + ').';
    return british(voice) ? 'Readout voice: ' + label : 'No British English voice listed; using ' + label;
  }
  function refreshVoice() {
    if (!canRead || active) return;
    try { $('voiceChoice').textContent = describeVoice(chooseVoice()); }
    catch { $('voiceChoice').textContent = 'The voice list is unavailable. You can try Read briefing again.'; }
  }
  function controls() {
    $('voiceListen').textContent = active ? 'Stop reading' : 'Read briefing';
    $('voiceListen').setAttribute('aria-label', active ? 'Stop reading JARVIS briefing' : 'Read JARVIS briefing aloud');
    $('voiceSpeak').textContent = recognizer ? 'Stop dictation' : 'Dictate agenda';
    $('voiceSpeak').setAttribute('aria-label', recognizer ? 'Stop agenda dictation' : 'Dictate a council agenda');
    $('voiceStop').disabled = !active && !recognizer;
  }
  function stopReading() {
    if (!active) return;
    active = null; // Ignore late cancellation events before another utterance starts.
    synth.cancel();
    controls();
  }
  function stopDictation() {
    if (!recognizer) return;
    const old = recognizer;
    recognizer = null;
    old.abort(); // Stop must not accept a late transcript.
    controls();
  }
  function setAgenda(text) {
    $('agenda').value = text;
    $('agenda').dispatchEvent(new Event('input')); // Invalidate any AI run preview.
  }

  $('voiceSpeak').disabled = !Recognition;
  $('voiceListen').disabled = !canRead;
  if (!Recognition) status('Agenda dictation is unavailable in this browser. Type your agenda and choose Run briefing.');
  if (!canRead) $('voiceChoice').textContent = 'Briefing readout is unavailable in this browser. The written briefing remains available.';
  else {
    synth.addEventListener('voiceschanged', refreshVoice);
    refreshVoice();
  }
  controls();

  $('voiceSpeak').onclick = () => {
    if (recognizer) { stopDictation(); status('Agenda dictation stopped.'); return; }
    if (!Recognition) return;
    stopReading();
    try {
      const current = new Recognition();
      recognizer = current;
      current.lang = 'en-US';
      current.interimResults = false;
      current.maxAlternatives = 1;
      current.onresult = event => {
        if (recognizer !== current) return;
        const transcript = event.results?.[0]?.[0]?.transcript?.trim().slice(0, 2000);
        if (!transcript) { status('No words were recognized. Type your agenda or try again.'); return; }
        $('voiceText').value = transcript;
        setAgenda(transcript);
        status('Agenda captured. Review the text, then choose Run briefing.');
      };
      current.onerror = () => {
        if (recognizer !== current) return;
        recognizer = null;
        controls();
        status('Dictation could not continue. Check microphone permission or type your agenda.');
      };
      current.onend = () => {
        if (recognizer !== current) return;
        recognizer = null;
        controls();
        if ($('voiceStatus').textContent.startsWith('Listening')) status('Dictation ended. Review your agenda or try again.');
      };
      current.start();
      controls();
      status('Listening for an agenda. Nothing runs until you choose Run briefing.');
    } catch {
      recognizer = null;
      controls();
      status('Dictation could not start. Check microphone permission or type your agenda.');
    }
  };

  $('voiceListen').onclick = () => {
    if (active) { stopReading(); status('Briefing readout stopped.'); return; }
    if (!canRead) return;
    stopDictation();
    const selected = $('meetingSummary').textContent.trim();
    const briefing = $('briefing').textContent.trim();
    const text = !selected || /select a meeting|reports will appear|reports and handoffs/i.test(selected) ? briefing : selected;
    if (!text || /your briefing will|run a briefing to prioritize|connect to/i.test(text)) {
      status('Run a briefing or select a meeting first, then choose Read briefing.');
      return;
    }
    try {
      const utter = new window.SpeechSynthesisUtterance('JARVIS briefing. ' + text.slice(0, 4000));
      utter.voice = chooseVoice(); // Fresh list even if voiceschanged never fires.
      utter.lang = utter.voice ? language(utter.voice) : 'en-GB';
      utter.rate = 0.94;
      utter.pitch = 0.87;
      const finish = message => {
        if (active !== utter) return;
        active = null;
        controls();
        status(message);
      };
      utter.onstart = () => { if (active === utter) status('Reading the briefing. Choose Stop reading to interrupt.'); };
      utter.onend = () => finish('Briefing readout finished.');
      utter.onerror = event => finish(['canceled', 'interrupted'].includes(event.error)
        ? 'Briefing readout stopped.'
        : 'Briefing readout could not play. Try again or check your device speech settings.');
      active = utter;
      controls();
      $('voiceChoice').textContent = describeVoice(utter.voice);
      status('Starting briefing readout…');
      synth.speak(utter); // Remain inside the user's tap; never autoplay on voice loading.
    } catch {
      active = null;
      controls();
      status('Briefing readout could not start. Try again or check your device speech settings.');
    }
  };

  $('voiceStop').onclick = () => {
    stopDictation();
    stopReading();
    status('Dictation and readout stopped.');
  };
  $('voiceRun').onclick = () => {
    const value = $('voiceText').value.trim();
    if (value) setAgenda(value.slice(0, 2000));
    if ($('review').disabled) { status('Connect your Swarm token first to run a briefing.'); return; }
    document.querySelector('[data-tab="council"]').click();
    $('rules').click();
    status('Rules briefing requested. Follow the meeting status below.');
  };
})();
