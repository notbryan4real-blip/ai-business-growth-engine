'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {createContext, runInContext} = require('node:vm');
const source = readFileSync(join(__dirname, '../dashboard/jarvis-missions.js'), 'utf8');
const html = readFileSync(join(__dirname, '../dashboard/jarvis.html'), 'utf8');

class Element extends EventTarget {
  constructor() { super(); this.value=''; this.textContent=''; this.children=[]; this.hidden=false; this.disabled=false; this.classList={toggle(){}}; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children=items; }
  click() { if (!this.disabled) return this.onclick?.(); }
}
const clone = value => JSON.parse(JSON.stringify(value));
const event = {preventDefault(){}};
function record(mode='ai', status='awaiting_start') {
  return {id:'saved-mission',goal:'Review print shop delivery',mode,status,created_at:'2026-10-28T12:00:00Z',
    plan_id:'a'.repeat(32), plan:{can_start:true,model_calls_required:mode==='ai'?3:0,model_calls_remaining:12,
    participants:['personal','qa','orchestrator'],fresh_sources:[],stale_sources:[],missing_sources:['gmail'],memory:[],memory_omitted:0,blockers:[]},
    events:[{at:'2026-10-28T12:00:00Z',action:'Plan saved'}],review:null,reports_available:true,
    result:status==='awaiting_start'?null:{meeting_id:'real-meeting',status:status==='interrupted'?'failed':'completed',summary:'Reviewed evidence',model_calls:mode==='ai'?3:0,
      actions:['Review this before sending'],risks:[],evidence_gaps:[]}};
}
async function setup(mission=record(), connect=true) {
  const nodes=Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],new Element()]));
  const requests=[], timers=[]; let current=clone(mission), serial=0;
  const response=async (path,options={}) => {
    const body=options.body?JSON.parse(options.body):null;
    requests.push({path,method:options.method||'GET',body});
    if(path==='/missions' && !options.method) return {missions:[current],metrics:{total:1,reviewed:current.review?1:0,owner_rated_useful:0},storage_notice:'Export before a restart.'};
    if(path==='/missions' && options.method==='POST') return clone(current);
    if(path.endsWith('/start')) { current={...current,status:'awaiting_review',result:record(current.mode,'awaiting_review').result}; return clone(current); }
    if(path.endsWith('/cancel')) { current={...current,status:'cancelled'}; return clone(current); }
    if(path.endsWith('/review')) { current={...current,status:'reviewed',review:{...body,input:body,lesson_id:body.lesson?'saved-lesson':null}}; return clone(current); }
    if(path.endsWith('/refresh')) { current={...current,plan_id:'b'.repeat(32)}; return clone(current); }
    if(path==='/missions/'+current.id) return clone(current);
    throw Error('Unexpected request: '+path);
  };
  const context=createContext({document:{hidden:false,getElementById:id=>nodes[id]},
    el:(tag,text)=>{const n=new Element();if(text!==undefined)n.textContent=text;return n;},
    request:(...args)=>response(...args),crypto:{randomUUID:()=> 'generated-request-'+(++serial)},
    setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout(){},
    load:async()=>{},openMeeting:async()=>{},tab(){}});
  runInContext(source,context);
  nodes.missionGoal.value=mission.goal; nodes.missionMode.value=mission.mode;
  if(connect) { runInContext('missionConnected()',context); await new Promise(resolve=>setImmediate(resolve)); }
  requests.length=0;
  return {nodes,requests,context,response,timers};
}

test('saving a mission shows its plan without starting a council', async()=>{
  const app=await setup(); await app.nodes.missionForm.onsubmit(event);
  assert.deepEqual(app.requests.filter(r=>r.method==='POST').map(r=>r.path),['/missions']);
  assert.equal(app.nodes.missionTitle.textContent,'Review print shop delivery');
  assert.equal(app.nodes.missionStart.hidden,false);
  assert.equal(app.nodes.missionReviewForm.hidden,true);
});
test('disconnected mission actions request a connection without making requests',async()=>{
  const app=await setup(record(),false);await app.nodes.missionForm.onsubmit(event);
  assert.equal(app.requests.length,0);assert.match(app.nodes.missionStatus.textContent,/Connect your Swarm/);
});
test('creation retries reuse the request ID after a lost response',async()=>{
  const app=await setup();const bodies=[];let first=true;
  app.context.request=async (path,options)=>{if(path==='/missions'&&options?.method==='POST'){bodies.push(JSON.parse(options.body));if(first){first=false;throw Error('Network interrupted');}}return app.response(path,options);};
  await app.nodes.missionForm.onsubmit(event);await app.nodes.missionForm.onsubmit(event);
  assert.equal(bodies.length,2);assert.equal(bodies[0].request_id,bodies[1].request_id);
});
test('start sends the reviewed plan ID and cap once despite repeated taps',async()=>{
  const app=await setup();await app.nodes.missionForm.onsubmit(event);let release;
  app.context.request=async(path,options)=>{if(path.endsWith('/start'))await new Promise(resolve=>{release=resolve;});return app.response(path,options);};
  const pending=app.nodes.missionStart.click();await app.nodes.missionStart.click();release();await pending;
  const calls=app.requests.filter(r=>r.path.endsWith('/start'));
  assert.equal(calls.length,1);assert.deepEqual(calls[0].body,{plan_id:'a'.repeat(32),approved_model_calls:3});
  assert.equal(app.nodes.missionReviewForm.hidden,false);
  assert.equal(app.nodes.missionLesson.value,'');
});
test('a blocked plan cannot start and refreshing replaces its approval version',async()=>{
  const blocked=record();blocked.plan.can_start=false;blocked.plan.blockers=['No provider configured'];
  const app=await setup(blocked);await app.nodes.missionForm.onsubmit(event);await app.nodes.missionStart.click();
  assert.equal(app.requests.filter(r=>r.path.endsWith('/start')).length,0);
  assert.equal(app.nodes.missionStart.disabled,true);
  const available=await setup();await available.nodes.missionForm.onsubmit(event);await available.nodes.missionReplan.click();await available.nodes.missionStart.click();
  assert.equal(available.requests.find(r=>r.path.endsWith('/start')).body.plan_id,'b'.repeat(32));
});
test('rules missions approve zero model calls and pause for an explicit review',async()=>{
  const app=await setup(record('rules'));await app.nodes.missionForm.onsubmit(event);await app.nodes.missionStart.click();
  assert.equal(app.requests.find(r=>r.path.endsWith('/start')).body.approved_model_calls,0);
  assert.equal(app.requests.filter(r=>r.path.endsWith('/review')).length,0);
  app.nodes.missionNote.value='The priorities are useful.';app.nodes.missionOutcome.value='useful';
  await app.nodes.missionReviewForm.onsubmit(event);
  assert.equal(app.requests.find(r=>r.path.endsWith('/review')).body.lesson,'');
  assert.match(app.nodes.missionStatus.textContent,/No lesson or external action/);
});
test('an interrupted mission offers review but cannot silently resume model calls',async()=>{
  const app=await setup(record('ai','interrupted'));await app.nodes.missionList.children[0].click();
  assert.equal(app.nodes.missionStart.hidden,true);assert.equal(app.nodes.missionReviewForm.hidden,false);
  assert.equal(app.nodes.missionOutcome.value,'needs_revision');assert.equal(app.nodes.missionOutcome.disabled,true);
  app.nodes.missionNote.value='Need fresh evidence and a new run.';await app.nodes.missionReviewForm.onsubmit(event);
  assert.equal(app.requests.filter(r=>r.path.endsWith('/start')).length,0);
  assert.equal(app.requests.find(r=>r.path.endsWith('/review')).body.outcome,'needs_revision');
});
test('stop does not create another run or automatically save model text as a lesson',async()=>{
  const app=await setup(record('ai','running'));await app.nodes.missionList.children[0].click();await app.nodes.missionCancel.click();
  assert.equal(app.requests.filter(r=>r.path.endsWith('/cancel')).length,1);
  assert.equal(app.requests.filter(r=>r.path.endsWith('/start')||r.path.endsWith('/review')).length,0);
  assert.equal(app.nodes.missionLesson.value,'');assert.equal(app.nodes.missionStart.hidden,true);
});
