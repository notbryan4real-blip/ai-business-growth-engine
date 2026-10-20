export const DEFAULT_API = location.hostname.endsWith('github.io')
  ? 'https://ai-business-growth-engine-api.onrender.com' : location.origin;
export const QUICK_AGENTS = ['qualification', 'audit', 'offer', 'sales', 'qa'];
export const AGENT_IDS = ['orchestrator','market','discovery','verification','competitive','qualification','audit','website','copywriting','pricing','sales_intel','outreach','project','customer_success','automation','finance','qa','offer','sales'];

export class SwarmClient {
  constructor(onEvent, onStatus) {
    this.onEvent = onEvent; this.onStatus = onStatus;
    this.base = localStorage.getItem('growth-engine-api-url') || DEFAULT_API;
    this.token = sessionStorage.getItem('growth-engine-api-token') || '';
    this.sequence = 0; this.polling = false; this.latest = null;
  }
  async request(path, options = {}) {
    const response = await fetch(this.base + path, {
      ...options, signal: AbortSignal.timeout(65000),
      headers: {'Content-Type':'application/json', 'Authorization':'Bearer '+this.token, ...options.headers}
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'API request failed ('+response.status+').');
    return data;
  }
  async connect(base, token) {
    const url = new URL(base.trim());
    if (url.protocol !== 'https:' && !(['localhost','127.0.0.1'].includes(url.hostname) && url.protocol === 'http:'))
      throw new Error('Use an HTTPS backend URL.');
    this.base = url.origin + url.pathname.replace(/\/$/, '');
    this.token = token.trim();
    if (!this.token) throw new Error('Enter your private API access token.');
    localStorage.setItem('growth-engine-api-url', this.base);
    sessionStorage.setItem('growth-engine-api-token', this.token);
    const health = await this.request('/api/health');
    if (!health.live_run_events) throw new Error('The backend needs the Swarm 0.2 upgrade before live runs can start.');
    await this.request('/api/approvals'); // Verify the private token before offering paid runs.
    this.catalog = (await this.request('/api/agents')).agents;
    this.onStatus('Connected · '+this.catalog.length+' roles · '+(health.ai_configured ? 'AI key configured' : 'AI key missing'));
    return health;
  }
  async start(prospect, agent_ids, audit_website = false) {
    const input = {prospect, agent_ids, audit_website};
    const saved = JSON.parse(sessionStorage.getItem('growth-engine-pending-request') || 'null');
    const request_id = saved?.base === this.base && JSON.stringify(saved.input) === JSON.stringify(input)
      ? saved.request_id : crypto.randomUUID();
    sessionStorage.setItem('growth-engine-pending-request', JSON.stringify({base:this.base, input, request_id}));
    const job = await this.request('/api/runs', {method:'POST', body:JSON.stringify({...input, request_id})});
    sessionStorage.removeItem('growth-engine-pending-request');
    sessionStorage.setItem('growth-engine-active-run', JSON.stringify({base:this.base, id:job.run_id}));
    this.sequence = 0;
    return this.watch(job.run_id);
  }
  async resume() {
    const active = JSON.parse(sessionStorage.getItem('growth-engine-active-run') || 'null');
    if (!active || active.base !== this.base) return false;
    this.sequence = 0;
    await this.watch(active.id);
    return true;
  }
  async watch(id) {
    if (this.polling) return;
    this.polling = true; this.runId = id;
    try {
      while (true) {
        const job = await this.request('/api/runs/'+encodeURIComponent(id)+'?after='+this.sequence);
        this.latest = job;
        for (const event of job.events) {this.onEvent(event); this.sequence = event.sequence;}
        this.onStatus(job.status+' · '+job.results.length+'/'+job.request.agent_ids.length+' agents · no outreach sent');
        if (!['queued','running'].includes(job.status)) {
          sessionStorage.removeItem('growth-engine-active-run');
          if (job.error) this.onStatus(job.status+': '+job.error);
          return job;
        }
        await new Promise(resolve => setTimeout(resolve, 1200));
      }
    } catch (error) {
      this.onStatus('Connection interrupted. Reconnect to resume this run. '+error.message);
      throw error;
    } finally {this.polling = false;}
  }
  async cancel() {
    if (this.runId) {
      await this.request('/api/runs/'+encodeURIComponent(this.runId)+'/cancel', {method:'POST'});
      this.onStatus('Stop requested. The current model call may finish; remaining calls will be skipped.');
    }
  }
}
