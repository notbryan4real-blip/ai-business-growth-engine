import {SwarmClient, QUICK_AGENTS, AGENT_IDS} from './swarm-client.js?v=0.2.1';
const get = id => document.getElementById(id);
async function loadPortfolioProject() {
  const id = new URLSearchParams(location.search).get('project');
  if (!id) return;
  const state = await client.request('/api/business/overview');
  const project = state.projects.find(p => p.id === id);
  if (!project) throw new Error('Portfolio project not found.');
  get('liveBusiness').value = project.name;
  get('liveIndustry').value = project.type;
  get('liveWebsite').value = project.url || '';
  const snapshot = project.snapshot;
  const notes = ['Portfolio project: '+project.id+'. Relationship: '+project.relationship+'.',
    'Objective: choose the next internal operational work toward a shared $1,000 weekly income goal. The target is not a forecast.',
    'This is a business operations review. Never invent sales, customers, connections or completed external actions.',
    'Recorded cash basis: '+JSON.stringify(state.money)];
  if (snapshot) {
    notes.push('Snapshot provenance: '+snapshot.source+' / '+snapshot.verification+' / '+snapshot.observed_at+'. Stale: '+project.snapshot_stale+'.',
      'Snapshot summary: '+snapshot.summary, 'Reported metrics, not verified cash: '+JSON.stringify(snapshot.metrics));
    if (snapshot.catalog.length) notes.push('Catalog totals: '+snapshot.catalog.length+' observed products; '+snapshot.catalog.filter(c=>c.status==='ACTIVE').length+' active; complete: '+snapshot.catalog_complete+'.');
  } else notes.push('No live operational snapshot. Identify the evidence needed; do not infer performance.');
  notes.push(...state.tasks.filter(t=>t.project_id===id&&t.status==='open').slice(0,5).map(t=>t.title+': '+t.details));
  get('liveEvidence').value = notes.join('\n').slice(0,10000);
  setStatus('Loaded '+project.name+' portfolio context. Choose the agent scope and start when ready.');
}
function setStatus(message, error=false) {
  get('liveStatus').textContent=message;
  get('liveFormStatus').textContent=message;
  get('liveFormStatus').dataset.error=String(error);
  if(error && !get('liveControls').classList.contains('hide'))
    get('liveFormStatus').scrollIntoView({block:'nearest'});
}
let transfers=0;
const client = new SwarmClient(event => {
  const active = AGENT_IDS.indexOf(event.agent_id);
  const phase = event.type === 'run_completed' ? 3 : event.agent_id === 'qa' ? 2 : event.type.startsWith('audit_') ? 0 : 1;
  ['s0','s1','s2','s3'].forEach((id, i)=>get(id).classList.toggle('active', i===phase));
  if (event.type === 'agent_started') {
    const previous = Math.max(0, AGENT_IDS.indexOf(event.source_agent_id));
    transfers++;
    get('packets').textContent=String(transfers).padStart(3,'0');
    window.swarmScene?.packet(previous, active);
    window.swarmScene?.inspect(active);
    get('name').textContent=event.name;
    get('picked').textContent=String(active).padStart(2,'0');
  }
  const row=document.createElement('div'); row.className='transfer';
  const heading=document.createElement('div'); heading.className='transfer-head';
  heading.textContent=event.sequence+' · '+event.type+' · '+event.timestamp.slice(11,19);
  const route=document.createElement('div'); route.className='transfer-route';
  route.textContent=event.name||event.url||'Run status';
  const pre=document.createElement('pre'); pre.textContent=JSON.stringify(event,null,2);
  row.append(heading,route,pre); get('streamLog').prepend(row);
  while(get('streamLog').children.length>30) get('streamLog').lastElementChild.remove();
  get('streamMeta').textContent='LIVE BACKEND EVENTS · '+transfers+' HANDOFFS';
  const line=document.createElement('div'); line.className='feedline';
  line.textContent=event.type==='agent_completed' ? event.name+': '+event.output.summary : event.type+' '+(event.name||'');
  get('feed').prepend(line); while(get('feed').children.length>4)get('feed').lastElementChild.remove();
}, status => {
  setStatus(status);
  get('systemStatus').textContent=/^(running|queued) ·/.test(status)?'● LIVE RUN':'● LIVE API';
  document.querySelector('.sys small').textContent='ACTUAL BACKEND EVENTS';
  if(client.latest) {
    const done=client.latest.results.length, total=client.latest.request.agent_ids.length;
    get('progressText').textContent=done+' / '+total+' agents';
    get('progressBar').style.width=(done/total*100)+'%';
    get('phase').textContent=String(done).padStart(2,'0');
  }
});
get('liveApi').value=client.base; get('liveToken').value=client.token;
if(new URLSearchParams(location.search).has('project')) get('liveControls').classList.remove('hide');
get('run').onclick=()=>get('liveControls').classList.remove('hide');
get('closeLive').onclick=()=>get('liveControls').classList.add('hide');
get('pause').onclick=async()=>{try{await client.cancel();}catch(e){setStatus(e.message,true);}};
get('next').onclick=()=>{
  if(!client.latest) {get('liveControls').classList.remove('hide');return;}
  const blob=new Blob([JSON.stringify(client.latest,null,2)],{type:'application/json'});
  const link=document.createElement('a'); link.href=URL.createObjectURL(blob);link.download='swarm-'+client.latest.run_id+'.json';link.click();
  setTimeout(()=>URL.revokeObjectURL(link.href),1000);
};
get('connectLive').onclick=async()=>{
  get('connectLive').disabled=true;
  setStatus('Checking backend and access token…');
  try {await client.connect(get('liveApi').value,get('liveToken').value);await loadPortfolioProject();transfers=0;get('streamLog').replaceChildren();await client.resume();}
  catch(e){setStatus(e.message,true);}
  finally{get('connectLive').disabled=false;}
};
get('liveForm').onsubmit=async event=>{
  event.preventDefault(); if(client.polling)return;
  get('startLive').disabled=true;
  get('startLive').textContent='Connecting…';
  setStatus('Checking backend before starting a paid run…');
  try {
    await client.connect(get('liveApi').value,get('liveToken').value);
    if(new URLSearchParams(location.search).has('project') && !get('liveBusiness').value) await loadPortfolioProject();
    transfers=0;get('streamLog').replaceChildren();
    if(await client.resume())return;
    const prospect={business_name:get('liveBusiness').value.trim(), category:get('liveIndustry').value.trim()||null,
      location:get('liveLocation').value.trim()||null,website_url:get('liveWebsite').value.trim()||null,
      verified_observations:get('liveEvidence').value.split(/\n+/).map(x=>x.trim()).filter(Boolean)};
    const ids=get('liveScope').value==='all'?client.catalog.map(a=>a.id):QUICK_AGENTS;
    transfers=0;get('streamLog').replaceChildren();
    get('liveControls').classList.add('hide');
    get('streamPanel').classList.remove('hide');
    await client.start(prospect,ids,Boolean(prospect.website_url));
  }catch(e){get('liveControls').classList.remove('hide');setStatus(e.message,true);}
  finally{get('startLive').disabled=false;get('startLive').textContent='Start live run';}
};
