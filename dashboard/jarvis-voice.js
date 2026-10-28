'use strict';
(()=>{
const $=id=>document.getElementById(id);
const status=msg=>{$('voiceStatus').textContent=msg;};
const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;
let recognizer=null;
$('voiceSpeak').onclick=()=>{
 if(!SpeechRecognition){status('Speech recognition is not supported in this browser. Type your request below instead.');$('voiceText').focus();return;}
 try{
  if(recognizer){recognizer.stop();recognizer=null;return;}
  recognizer=new SpeechRecognition();recognizer.lang='en-US';recognizer.interimResults=false;recognizer.maxAlternatives=1;
  recognizer.onresult=e=>{const transcript=e.results[0][0].transcript;$('voiceText').value=transcript;$('agenda').value=transcript;status('Heard: '+transcript+' — tap Run briefing to proceed.');};
  recognizer.onerror=e=>status('Microphone unavailable: '+e.error+'. You can type instead.');
  recognizer.onend=()=>{recognizer=null;};
  recognizer.start();status('Listening… speak your agenda.');
 }catch(e){status('Microphone unavailable: '+e.message);}
};
$('voiceListen').onclick=()=>{
 if(!('speechSynthesis' in window)){status('Speech playback is unavailable in this browser.');return;}
 speechSynthesis.cancel();
 const text=($('meetingSummary').textContent||'').trim();
 const briefing=($('briefing').textContent||'').trim();
 const speech=/select a meeting|reports and handoffs/i.test(text)?briefing:(text||briefing);
 if(!speech||/connect to|your briefing will/i.test(speech)){status('Connect and run a briefing first, then tap Listen.');return;}
 const u=new SpeechSynthesisUtterance('Good day. Here is your briefing. '+speech.slice(0,4000));u.lang='en-US';u.rate=.94;u.pitch=.87;
 const voices=speechSynthesis.getVoices();u.voice=voices.find(v=>v.lang.startsWith('en')&&/male|daniel|david|google uk english male/i.test(v.name))||voices.find(v=>v.lang.startsWith('en-GB'))||voices.find(v=>v.lang.startsWith('en'))||null;
 u.onerror=()=>status('Speech playback failed. Your written briefing remains available.');
 u.onend=()=>status('Briefing playback finished.');
 speechSynthesis.speak(u);status('JARVIS speaking. Tap Stop to interrupt.');
};
$('voiceStop').onclick=()=>{recognizer?.stop();if('speechSynthesis'in window)speechSynthesis.cancel();status('Voice stopped.');};
$('voiceRun').onclick=()=>{
 const value=$('voiceText').value.trim();
 if(value)$('agenda').value=value;
 if(!$('review').disabled){document.querySelector('[data-tab="council"]').click();$('rules').click();status('Running rules-mode council meeting.');}
 else status('Connect your Swarm token first to run a meeting.');
};
})();