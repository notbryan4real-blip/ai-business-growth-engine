import {SwarmClient} from './swarm-client.js';
const byId = id => document.getElementById(id);
const client = new SwarmClient(event => {
  const output = byId('agentOutput');
  if (event.type === 'agent_started') output.textContent += '\n→ '+event.name+'\n';
  if (event.type === 'agent_completed') output.textContent += JSON.stringify(event.output, null, 2)+'\n';
  if (event.type === 'audit_completed') output.textContent += 'Website audit: '+JSON.stringify(event.audit, null, 2)+'\n';
}, status => {byId('agentRunStatus').textContent = status;});
byId('agentApiUrl').value = client.base;
byId('agentApiToken').value = client.token;
async function connect() {
  await client.connect(byId('agentApiUrl').value, byId('agentApiToken').value);
  const container = document.querySelector('input[name="agentIds"]').closest('.stack');
  const chosen = new Set([...container.querySelectorAll('input:checked')].map(x=>x.value));
  container.replaceChildren();
  for (const agent of client.catalog) {
    const label = document.createElement('label'); label.className='checkrow';
    const box = document.createElement('input'); box.type='checkbox'; box.name='agentIds'; box.value=agent.id;
    box.checked=chosen.has(agent.id); label.append(box, document.createTextNode(agent.name)); container.append(label);
  }
}
byId('checkAgentsConnection').onclick = async () => {
  try {await connect(); await client.resume();} catch(e) {byId('agentRunStatus').textContent=e.message;}
};
byId('agentForm').addEventListener('submit', async event => {
  event.preventDefault(); if (client.polling) return;
  const button = byId('runAgentsBtn'); button.disabled=true;
  try {
    await connect();
    if (await client.resume()) return;
    const ids=[...document.querySelectorAll('input[name="agentIds"]:checked')].map(x=>x.value);
    if (!ids.length) throw new Error('Select at least one agent.');
    const prospect={business_name:byId('agentBusiness').value.trim(),category:byId('agentIndustry').value.trim()||null,
      location:byId('agentLocation').value.trim()||null,website_url:byId('agentWebsite').value.trim()||null,
      verified_observations:byId('agentEvidence').value.split(/\n+/).map(x=>x.trim()).filter(Boolean)};
    byId('agentOutput').textContent='Starting live run…\n';
    await client.start(prospect, ids, Boolean(prospect.website_url));
  } catch(e) {byId('agentRunStatus').textContent=e.message;}
  finally {button.disabled=false;}
});
