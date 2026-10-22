'use strict';
const $=id=>document.getElementById(id);
const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const money=value=>Number(value).toLocaleString(undefined,{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:2});
const date=value=>value?new Date(value).toLocaleString(): '—';
let state=null,catalog=null,latest=null,replayResult=null,connected=false,running=false,selectedStage=null;
const localDate=()=>new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);
const defaultBase=location.hostname==='localhost'||location.hostname==='127.0.0.1'||location.hostname.endsWith('onrender.com')?location.origin:'https://ai-business-growth-engine-api.onrender.com';
$('api').value=localStorage.getItem('growth-engine-api-url')||defaultBase;
$('token').value=sessionStorage.getItem('growth-engine-api-token')||'';
$('published').value=localDate();
function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
function base(){const u=new URL($('api').value.trim());if(u.username||u.password||u.search||u.hash)throw Error('Use a plain HTTPS backend URL.');if(u.protocol!=='https:'&&!(u.protocol==='http:'&&['localhost','127.0.0.1'].includes(u.hostname)))throw Error('Use an HTTPS backend URL.');return u.origin+u.pathname.replace(/\/$/,'');}
async function request(path,options={},publicRead=false){
 const headers={'Content-Type':'application/json'};
 if(!publicRead){const token=$('token').value.trim();if(!token)throw Error('Open Connect your existing Swarm and enter your private token.');headers.Authorization='Bearer '+token;}
 const response=await fetch(base()+'/api/reactor'+path,{...options,headers,signal:AbortSignal.timeout(65000)});
 const data=await response.json().catch(()=>({}));
 if(!response.ok){const message=typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.slice(0,3).map(d=>d.loc.slice(1).join('.')+': '+d.msg).join(' · '):response.status===404?'The Reactor backend is not deployed at this URL yet.':'Request failed ('+response.status+').';throw Error(message);}
 return data;
}
async function action(fn){try{await fn();}catch(e){status(e.name==='TimeoutError'?'The host took too long to respond. It may be waking up; retry using the same saved request.':e.message,true);}}
function saveFile(data,filename){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
document.querySelectorAll('[data-tab]').forEach(button=>button.onclick=()=>{document.querySelectorAll('[role=tabpanel]').forEach(p=>p.hidden=p.id!==button.dataset.tab);document.querySelectorAll('[role=tab]').forEach(b=>b.setAttribute('aria-selected',String(b===button)));if(button.dataset.tab==='live')drawChart();});
const svgNS='http://www.w3.org/2000/svg';
function svg(tag,attributes,text){const el=document.createElementNS(svgNS,tag);for(const [k,v]of Object.entries(attributes))el.setAttribute(k,String(v));if(text!==undefined)el.textContent=text;return el;}
function buildRing(){
 const points=catalog.agents.map((a,i)=>({x:300+172*Math.cos(-Math.PI/2+i*Math.PI/4),y:245+172*Math.sin(-Math.PI/2+i*Math.PI/4)}));
 $('ringEdges').replaceChildren();$('ringNodes').replaceChildren();
 catalog.agents.forEach((agent,i)=>{const p=points[i],next=points[(i+1)%8];$('ringEdges').append(svg('line',{x1:p.x,y1:p.y,x2:next.x,y2:next.y,class:'ring-edge','data-stage':agent.id}));
  const group=svg('g',{class:'ring-node','data-stage':agent.id,tabindex:0,role:'button','aria-label':agent.name+' stage'});
  group.append(svg('circle',{cx:p.x,cy:p.y,r:27}),svg('text',{x:p.x,y:p.y+5,'text-anchor':'middle',class:'number'},String(i+1).padStart(2,'0')),svg('text',{x:p.x,y:p.y+45,'text-anchor':'middle'},agent.name.toUpperCase()));
  const choose=()=>{selectedStage=agent.id;renderStage();};group.onclick=choose;group.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose();}};$('ringNodes').append(group);
 });
 $('strategies').replaceChildren();catalog.strategies.forEach((s,i)=>{const card=node('article',undefined,'strategy');card.append(node('span','0'+(i+1),'eyebrow'),node('h3',s.name),node('p',s.detail));$('strategies').append(card);});
 $('modelName').textContent='Board: '+catalog.board_model+' · workers: '+catalog.worker_model+' · '+(catalog.ai_key_configured?'key configured; credit not verified':'key not configured');
}
function renderStage(){
 const agent=catalog?.agents.find(a=>a.id===selectedStage),msg=latest?.messages?.find(m=>m.from===selectedStage);
 document.querySelectorAll('.ring-node').forEach(n=>n.classList.toggle('selected',n.dataset.stage===selectedStage));
 $('stageDetail').textContent=msg?agent.name+' → '+msg.to+' · '+msg.elapsed_ms+' ms · '+date(msg.at):agent?agent.purpose+' No recorded output selected.':'Select a stage to inspect its recorded output.';
 $('stageData').hidden=!msg;if(msg)$('stageData').textContent=JSON.stringify({data:msg.data,model_review:msg.model_review},null,2);
}
function renderRun(run){
 latest=run;$('cycleStatus').textContent=run.status.toUpperCase();$('reportTitle').textContent=run.status==='completed'?'Decision recorded.':run.status==='failed'?'Cycle stopped.':'Processing evidence…';
 $('reportSummary').textContent=run.error||run.summary||'Reading sources and passing structured evidence through the ring.';$('elapsed').textContent=run.elapsed_ms?Math.round(run.elapsed_ms)+' ms total':'';
 const complete=new Set(run.messages.map(m=>m.from));document.querySelectorAll('.ring-node,.ring-edge').forEach(n=>n.classList.toggle('completed',complete.has(n.dataset.stage)));
 $('boardMode').textContent=run.request.board==='full_ai'?'FULL AI':run.request.board==='ai'?'AI REVIEW':'RULES';const totalCalls=(run.worker_model_calls||0)+run.board.model_calls;$('boardCalls').textContent=totalCalls+' model call'+(totalCalls===1?'':'s');
 const decisions=run.assessment?.decisions||run.messages.find(m=>m.from==='analyst')?.data?.decisions||[];
 $('decisions').replaceChildren();
 for(const d of decisions){const card=node('article',undefined,'decision'),head=node('div',undefined,'decision-head');head.append(node('strong',d.asset),node('span',d.action.replaceAll('_',' ').toUpperCase(),'badge '+(d.action==='avoid'?'bad':d.action==='paper_candidate'?'good':'')));card.append(head,node('p','Score '+d.score+' · '+d.supporting_strategies+' supporting strategy types'));
  for(const g of d.evidence.slice(0,3))card.append(node('p',g.kind+': '+g.reason));$('decisions').append(card);}
 if(!decisions.length)$('decisions').append(node('p','No eligible evidence to assess yet. Missing feeds do not become signals.','hint'));
 if(run.paper_result?.blocked?.length)$('decisions').append(node('p',run.paper_result.blocked.join(' · '),'hint'));
 selectedStage=selectedStage||run.messages.at(-1)?.from;renderStage();
}
function drawChart(){
 const canvas=$('equityChart'),rect=canvas.getBoundingClientRect();if(rect.width<1)return;
 const ratio=window.devicePixelRatio||1;canvas.width=rect.width*ratio;canvas.height=180*ratio;const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);const width=rect.width,height=180;ctx.clearRect(0,0,width,height);
 const rows=state?.paper?.curve||[];if(!rows.length){ctx.fillStyle='#91a29c';ctx.font='12px system-ui';ctx.fillText('No recorded cycles yet.',12,85);return;}
 const values=[state.paper.initial_cash,...rows.map(r=>r.equity)],min=Math.min(...values),max=Math.max(...values),range=Math.max(max-min,1),lo=min-range*.15,hi=max+range*.15;
 const x=i=>55+i/Math.max(1,values.length-1)*(width-65),y=v=>145-(v-lo)/(hi-lo)*125;
 ctx.font='10px monospace';for(let i=0;i<3;i++){const value=lo+(hi-lo)*i/2;ctx.strokeStyle='#283234';ctx.beginPath();ctx.moveTo(53,y(value));ctx.lineTo(width-8,y(value));ctx.stroke();ctx.fillStyle='#91a29c';ctx.fillText('$'+value.toFixed(1),0,y(value)+4);}
 ctx.strokeStyle='#b5ec7b';ctx.lineWidth=2;ctx.beginPath();values.forEach((v,i)=>i?ctx.lineTo(x(i),y(v)):ctx.moveTo(x(i),y(v)));ctx.stroke();
 $('chartNote').textContent=rows.length+' recorded marks · '+(rows.at(-1).quotes_complete?'latest holdings marked with fresh quotes':'latest mark includes stale holdings');
}
const riskFields=[['initial_cash','Starting paper cash ($)',10,100000,1],['position_cap_pct','Max position (%)',1,20,.5],['exposure_cap_pct','Max total exposure (%)',1,50,1],['risk_per_trade_pct','Risk budget per trade (%)',.1,1,.1],['daily_loss_pct','Daily loss limit (%)',.5,5,.5],['max_drawdown_pct','Max drawdown (%)',1,15,1],['stop_loss_pct','Stop trigger (%)',.5,10,.5],['take_profit_pct','Profit trigger (%)',1,20,.5],['max_hold_hours','Time exit (hours)',1,48,1],['fee_bps','Fee per side (basis points)',0,200,1],['slippage_bps','Slippage per side (basis points)',0,200,1],['daily_board_call_limit','All Reactor model calls per day',0,24,1]];
for(const [key,label,min,max,step]of riskFields){const field=node('label',label),input=node('input');Object.assign(input,{type:'number',id:'setting-'+key,min,max,step,required:true});field.append(input);$('riskFields').append(field);}
function enable(){for(const id of ['refresh','saveEvidence','importEvidence','runReplay','saveSettings','export'])$(id).disabled=!connected;$('run').disabled=!connected||running;$('aiRun').disabled=!connected||running||!catalog?.ai_key_configured;$('fullRun').disabled=!connected||running||!catalog?.ai_key_configured||((state?.settings.daily_board_call_limit||0)-(state?.board_calls_reserved_today||0)<9);}
async function load(){state=await request('/overview');connected=true;renderState();enable();}
function renderState(){
 const p=state.paper;$('equity').textContent=money(p.equity);$('capitalNote').textContent=money(p.initial_cash)+' starting virtual capital';$('pnl').textContent=money(p.equity-p.initial_cash);$('pnl').className=p.equity>=p.initial_cash?'good':'bad';$('drawdown').textContent=p.max_drawdown_pct.toFixed(2)+'%';$('riskState').textContent=p.halted?'HALTED · '+p.halt_reason:state.settings.paused?'New entries paused':'Paper risk controls active';$('closedTrades').textContent=p.trades.filter(t=>t.side==='sell').length;$('fees').textContent=money(p.fees_paid)+' fees paid';
 $('connectionState').textContent='Private workspace connected';$('modeNote').textContent=state.settings.automatic_paper?'Automatic paper · host must be awake':'Manual paper cycles';$('storage').textContent=state.storage.durable_configured?'Durable storage is configured. Export a private backup regularly.':state.storage.notice;
 for(const [key]of riskFields)$('setting-'+key).value=state.settings[key];$('automatic').checked=state.settings.automatic_paper;$('paused').checked=state.settings.paused;
 $('history').replaceChildren();for(const run of state.runs){const button=node('button',run.status+' · '+date(run.created_at));button.append(node('span',run.summary||run.error||run.mode));button.onclick=()=>action(async()=>{renderRun(await request('/runs/'+encodeURIComponent(run.id)));});$('history').append(button);}if(!state.runs.length)$('history').append(node('p','No cycles recorded yet.','hint'));
 $('trades').replaceChildren();for(const t of p.trades.slice(-40).reverse()){const tr=node('tr');for(const value of [date(t.at),t.asset,t.side.toUpperCase(),money(t.price),money(t.fee),t.pnl===undefined?'—':money(t.pnl),t.reason.replaceAll('_',' ')])tr.append(node('td',value));$('trades').append(tr);}
 if(!p.trades.length){const tr=node('tr'),td=node('td','No paper fills recorded. Waiting is a valid result.');td.colSpan=7;tr.append(td);$('trades').append(tr);}
 $('evidenceList').replaceChildren();for(const e of state.events){const row=node('article',undefined,'item');row.append(node('strong',e.asset+' · '+e.kind),node('p',e.headline||e.reference),node('p',e.provenance+' · observed '+date(e.observed_at)));const a=node('a','Original source ↗');a.href=e.source_url;a.target='_blank';a.rel='noopener noreferrer';row.append(a);$('evidenceList').append(row);}if(!state.events.length)$('evidenceList').append(node('p','Run a cycle to record public feeds, or add sourced evidence here.','hint'));drawChart();
}
function renderMarket(data){
 $('quotes').replaceChildren();for(const asset of ['BTC','ETH','AAVE','UNI']){const q=data.quotes[asset],card=node('article',undefined,'quote');card.append(node('span',asset+' / USD','asset'),node('strong',q?money(q.price):'Unavailable'));card.append(node('small',q?new Date(q.quote_at).toLocaleTimeString():'No fresh quote'),node('small',q?'Spread '+q.spread_bps+' bps':'Entries blocked'));$('quotes').append(card);}
 $('feedStatus').replaceChildren();for(const [name,result]of Object.entries(data.sources)){const row=node('div',undefined,'source-row'),left=node('div',name.replaceAll('_',' '));if(result.detail)left.append(node('p',result.detail,'hint'));row.append(left,node('span',result.status.replaceAll('_',' '),result.status==='ok'?'good':'hint'));$('feedStatus').append(row);}
 const ok=Object.values(data.sources).filter(s=>s.status==='ok').length;$('sourceSummary').textContent=ok+' source checks succeeded · fetched '+date(data.fetched_at)+' · 90-second cache · Coinbase quotes, DefiLlama revenue, SEC headlines';
}
async function refreshMarket(){status('Reading public sources. The host may need a moment to wake up.');const data=await request('/market',{},true);renderMarket(data);status('Public source checks complete. Missing and stale inputs are marked explicitly.');}
$('refreshMarket').onclick=()=>action(refreshMarket);
$('connectForm').onsubmit=e=>{e.preventDefault();action(async()=>{status('Connecting to your private workspace…');catalog=await request('/status',{},true);buildRing();await load();localStorage.setItem('growth-engine-api-url',base());sessionStorage.setItem('growth-engine-api-token',$('token').value.trim());$('connection').open=false;status('Connected. Ready to record paper research.');if(state.runs[0])renderRun(await request('/runs/'+state.runs[0].id));resume();});};
$('refresh').onclick=()=>action(async()=>{await load();status('Private record refreshed.');});
async function watch(id){if(running)return;running=true;enable();try{while(true){const run=await request('/runs/'+encodeURIComponent(id));renderRun(run);if(!['queued','running'].includes(run.status)){sessionStorage.removeItem('reactor-active');sessionStorage.removeItem('reactor-pending');await load();status(run.error||'Cycle complete. '+run.summary,Boolean(run.error));break;}await new Promise(resolve=>setTimeout(resolve,1000));}}finally{running=false;enable();}}
function stored(key){try{return JSON.parse(sessionStorage.getItem(key)||'null');}catch{return null;}}
async function start(board){if(running)return;const old=stored('reactor-pending'),requestBody=old?.base===base()&&old.body.board===board?old.body:{request_id:crypto.randomUUID(),board,paper_execute:true};sessionStorage.setItem('reactor-pending',JSON.stringify({base:base(),body:requestBody}));status('Starting paper research. No exchange orders are available.');const run=await request('/runs',{method:'POST',body:JSON.stringify(requestBody)});sessionStorage.setItem('reactor-active',JSON.stringify({base:base(),id:run.id}));await watch(run.id);}
function resume(){const old=stored('reactor-active');if(old?.base===base())action(()=>watch(old.id));}
$('run').onclick=()=>action(()=>start('rules'));$('aiRun').onclick=()=>action(()=>start('ai'));$('fullRun').onclick=()=>action(()=>start('full_ai'));
const help={unlock:['{"unlock_pct_float": 0, "unlock_to_daily_volume": 0}','Percentage of circulating supply and unlock USD value divided by daily traded USD volume. Set the scheduled unlock time.'],revenue:['{"recent_7d_usd": 0, "previous_7d_usd": 0}','Two consecutive completed seven-day revenue totals. Set measurement end time.'],regulation:['{}','Paste the exact headline from an official regulator. No numerical metrics; use {}.'],listing:['{"stage": "roadmap"}','Allowed stages: roadmap, announced, trading, observed_pair. Use an official exchange source.'],miner:['{"outflow_multiple": 0}','Miner outflow divided by its historical baseline. Set measurement end time. Transfers are not necessarily sales.']};
function metricHelp(){const [placeholder,text]=help[$('kind').value];$('metrics').placeholder=placeholder;$('metricHelp').textContent=text;$('eventAt').required=['unlock','revenue'].includes($('kind').value);}
$('kind').onchange=metricHelp;metricHelp();
$('evidenceForm').onsubmit=e=>{e.preventDefault();action(async()=>{const event={reference:'owner-'+crypto.randomUUID(),kind:$('kind').value,asset:$('asset').value.trim(),source_url:$('sourceUrl').value.trim(),published_at:new Date($('published').value).toISOString(),observed_at:new Date().toISOString(),event_at:$('eventAt').value?new Date($('eventAt').value).toISOString():null,headline:$('headline').value.trim(),metrics:JSON.parse($('metrics').value),confirmed:$('confirmed').checked};await request('/evidence',{method:'POST',body:JSON.stringify({events:[event]})});await load();status('Evidence saved with provenance. Run a cycle to evaluate it.');});};
async function readFile(input,limit){const file=input.files[0];if(!file||file.size>limit)throw Error('Choose a JSON file smaller than '+Math.round(limit/1000)+' KB.');return JSON.parse(await file.text());}
$('importForm').onsubmit=e=>{e.preventDefault();action(async()=>{const data=await readFile($('importFile'),500000);const result=await request('/evidence',{method:'POST',body:JSON.stringify(data)});await load();status(result.accepted+' evidence records accepted.');});};
$('settingsForm').onsubmit=e=>{e.preventDefault();action(async()=>{const values={...state.settings};for(const [key]of riskFields)values[key]=Number($('setting-'+key).value);values.automatic_paper=$('automatic').checked;values.paused=$('paused').checked;await request('/settings',{method:'PUT',body:JSON.stringify(values)});await load();status('Controls saved. Pausing entries does not stop risk exits.');});};
$('export').onclick=()=>action(async()=>{saveFile(await request('/export'),'reactor-private-backup-'+new Date().toISOString().slice(0,10)+'.json');status('Private research and paper records exported.');});
$('replayForm').onsubmit=e=>{e.preventDefault();action(async()=>{const data=await readFile($('replayFile'),1500000);status('Testing event timing and the untouched holdout…');replayResult=await request('/replay',{method:'POST',body:JSON.stringify(data)});$('replayResult').replaceChildren();for(const [key,title]of [['full_period','Full period'],['holdout','Untouched holdout']]){const r=replayResult[key],card=node('article',undefined,'decision');card.append(node('h3',title),node('p','Net P&L '+money(r.net_pnl)+' · drawdown '+r.max_drawdown_pct+'%'),node('p',r.closed_trades+' closed trades · fees '+money(r.fees_paid)),node('p','Buy-and-hold net P&L '+money(r.buy_hold_net_pnl)));$('replayResult').append(card);}$('replayResult').append(node('p',replayResult.conclusion,'hint'));$('exportReplay').hidden=false;status('Historical test complete. Input authenticity remains the dataset owner’s responsibility.');});};
$('exportReplay').onclick=()=>saveFile(replayResult,'reactor-event-replay.json');
window.addEventListener('resize',drawChart);
action(async()=>{catalog=await request('/status',{},true);buildRing();status('Reactor is available. Refresh public feeds or connect your private workspace.');if($('token').value){await load();$('connection').open=false;if(state.runs[0])renderRun(await request('/runs/'+state.runs[0].id));resume();}else $('connection').open=true;await refreshMarket();});
