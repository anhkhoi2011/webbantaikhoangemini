const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('index.html', 'utf8');
const source = html.slice(html.indexOf('    const visitsInFlight = new Set();'), html.indexOf('    const visitorReady = captureVisitorIpSilently();'));
const visit = {visitId: 'PAGE-A', sessionId: 'SESSION-A', fullUrl: 'https://shop.example/?utm_source=facebook', domain: 'shop.example', referrer: 'Facebook', utmSource: 'facebook', ip: '', location: ''};
function storage() {
  const items = {};
  Object.defineProperties(items, {
    getItem: {value: key => items[key] ?? null},
    setItem: {value: (key, value) => { items[key] = String(value); }},
    removeItem: {value: key => { delete items[key]; }}
  });
  return items;
}
function context(backend, fallback) {
  const localStorage = storage(), sessionStorage = storage();
  const ctx = {URL, AbortSignal, console, localStorage, sessionStorage,
    CONFIG: {googleAppsScriptUrl: 'https://example.invalid/sheet'},
    visitorData: {...visit}, smartApiFetch: backend,
    fetch: fallback || (async () => { throw Error('Unexpected outbound request'); })};
  vm.createContext(ctx);
  vm.runInContext(source, ctx);
  return ctx;
}
const key = 'crm_visit_retry_PAGE-A';
const ack = id => ({ok: true, json: async () => ({status: 'success', visitId: id})});
async function run() {
  let calls = [];
  let ctx = context(async (path, opts) => { calls.push(JSON.parse(opts.body)); return ack('PAGE-A'); });
  ctx.localStorage.setItem(key, JSON.stringify(visit));
  await ctx.syncVisitor(visit);
  assert.equal(ctx.localStorage.getItem(key), null);
  assert.equal(calls[0].visitId, 'PAGE-A');
  assert.equal(calls[0].fullUrl, visit.fullUrl);

  let fallbackPosts = [], backendAvailable = false;
  ctx = context(async () => backendAvailable ? ack('PAGE-A') : {ok: false, status: 404}, async (url, opts) => {
    if (url.endsWith('?action=health')) return {json: async () => ({protocolVersion: 2, trafficColumns: 25})};
    fallbackPosts.push(JSON.parse(opts.body)); return {type: 'opaque'};
  });
  ctx.localStorage.setItem(key, JSON.stringify(visit));
  await ctx.syncVisitor(visit); await ctx.retryVisits();
  assert.equal(fallbackPosts.length, 2);
  assert.ok(fallbackPosts.every(p => p.visitId === 'PAGE-A' && p.fullUrl === visit.fullUrl));
  assert.ok(ctx.localStorage.getItem(key), 'opaque response must retain retry');
  backendAvailable = true; await ctx.retryVisits();
  assert.equal(ctx.localStorage.getItem(key), null);

  let fallbackCalls = 0;
  ctx = context(async () => ({ok: false, status: 409}), async () => { fallbackCalls++; });
  ctx.localStorage.setItem(key, JSON.stringify(visit));
  await ctx.syncVisitor(visit);
  assert.equal(fallbackCalls, 0, 'do not bypass backend rejection');
  ctx = context(async () => ({ok: false, status: 404}), async (url, opts) => {
    if (!url.endsWith('?action=health')) fallbackCalls++;
    return {json: async () => ({protocolVersion: 2, columns: 40})};
  });
  await ctx.syncVisitor(visit);
  assert.equal(fallbackCalls, 0, 'old Apps Script must not receive retryable visits');

  let resolveFirst;
  calls = [];
  ctx = context(async (path, opts) => {
    calls.push(JSON.parse(opts.body));
    if (calls.length === 1) return new Promise(resolve => { resolveFirst = resolve; });
    return ack('PAGE-A');
  });
  ctx.localStorage.setItem(key, JSON.stringify(visit));
  const initial = ctx.syncVisitor(visit);
  const enriched = {...visit, ip: '203.0.113.7', location: 'Test city'};
  ctx.recordVisit(enriched);
  resolveFirst(ack('PAGE-A')); await initial;
  assert.equal(JSON.parse(ctx.localStorage.getItem(key)).ip, enriched.ip, 'older ack must not discard enrichment');
  await ctx.retryVisits();
  assert.equal(calls.length, 2); assert.equal(calls[1].ip, enriched.ip);
  assert.equal(ctx.localStorage.getItem(key), null);
  assert.equal(JSON.parse(ctx.localStorage.getItem('crm_visits')).length, 1);

  let resolveIp;
  calls = [];
  ctx = context(async (path, opts) => { calls.push(JSON.parse(opts.body)); return ack(JSON.parse(opts.body).visitId); }, async () => new Promise(resolve => { resolveIp = resolve; }));
  const original = ctx.visitorData;
  const capturing = ctx.captureVisitorIpSilently();
  assert.equal(calls.length, 1, 'first visit must be sent before IP lookup');
  ctx.visitorData = {...visit, visitId: 'PAGE-B', fullUrl: 'https://shop.example/?utm_source=zalo', referrer: 'Zalo Chat', utmSource: 'zalo'};
  resolveIp({ok: true, json: async () => ({success: true, ip: '203.0.113.9', city: 'Test city', country: 'Test country'})});
  await capturing;
  await ctx.retryVisits();
  assert.ok(calls.every(p => p.visitId === 'PAGE-A' && p.fullUrl === visit.fullUrl && p.utmSource === 'facebook'));
  assert.equal(original.ip, '203.0.113.9');
  assert.equal(ctx.visitorData.visitId, 'PAGE-B');
  assert.equal(ctx.visitorData.ip, '', 'late lookup must not mutate another visit');
  assert.equal(JSON.parse(ctx.localStorage.getItem('crm_visits')).length, 1);
  console.log('PASS visit sync: immediate capture, opaque retries, old-script guard, rejection, in-flight enrichment and navigation isolation');
}
run().catch(err => { console.error(err); process.exitCode = 1; });
