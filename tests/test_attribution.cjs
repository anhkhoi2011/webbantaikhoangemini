const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const html = fs.readFileSync('index.html', 'utf8');
const source = html.slice(html.indexOf('    function getTrafficSource('), html.indexOf('    const completingOrders = new Set();'));
const storage = new Map();
let clock = Date.parse('2026-10-23T06:00:00Z');
function visit(href, rawReferrer = '', navigationType = 'navigate', store = storage, afterLoad) {
  class ClockDate extends Date { constructor(...args) { super(...(args.length ? args : [clock])); } static now() { return clock; } }
  const location = new URL(href);
  const ctx = {URL, URLSearchParams, crypto, Date: ClockDate,
    window: {location}, document: {referrer: rawReferrer}, navigator: {userAgent: 'Mobile Safari/18'},
    performance: {getEntriesByType: () => [{type: navigationType}]},
    sessionStorage: {getItem: key => store.get(key) || null, setItem: (key, value) => store.set(key, value)}};
  vm.createContext(ctx);
  vm.runInContext(source + '\nglobalThis.result = orderTracking();', ctx);
  if (afterLoad) { afterLoad(ctx); vm.runInContext('globalThis.result = orderTracking();', ctx); }
  clock += 1000;
  return ctx.result;
}
const zaloLink = 'https://shop.example/?zarsrc=31&utm_source=zalo&utm_medium=zalo&utm_campaign=zalo';
const zalo = visit(zaloLink);
assert.equal(zalo.referrer, 'Zalo Chat'); assert.equal(zalo.isFromAd, false);
const reload = visit(zaloLink, '', 'reload');
assert.notEqual(reload.visitId, zalo.visitId); assert.notEqual(reload.visitedAt, zalo.visitedAt);
assert.equal(reload.sessionId, zalo.sessionId); assert.equal(reload.landingAt, zalo.landingAt);
const facebook = visit('https://shop.example/?ref=facebook', zaloLink);
assert.equal(facebook.referrer, 'Facebook'); assert.equal(facebook.utmSource, '');
assert.notEqual(facebook.visitId, zalo.visitId);
assert.equal(facebook.utmCampaign, ''); assert.notEqual(facebook.sessionId, zalo.sessionId);
assert.equal(facebook.fullUrl, 'https://shop.example/?ref=facebook');
const direct = visit('https://shop.example/');
assert.equal(direct.referrer, 'Truy cập trực tiếp'); assert.equal(direct.utmCampaign, '');
const external = visit('https://shop.example/', 'https://facebook.com/');
const externalReload = visit('https://shop.example/', '', 'reload');
assert.equal(externalReload.referrer, 'Facebook'); assert.equal(externalReload.landingAt, external.landingAt);
assert.equal(visit('https://shop.example/', 'https://google.com/').referrer, 'Tìm kiếm Google');
const sourceOnly = visit('https://shop.example/?source=tiktok');
assert.equal(sourceOnly.referrer, 'TikTok');
const campaignOnly = visit('https://shop.example/?utm_campaign=new_campaign');
assert.equal(campaignOnly.referrer, 'Truy cập trực tiếp'); assert.equal(campaignOnly.utmCampaign, 'new_campaign');
const google = visit('https://shop.example/?utm_source=google&utm_medium=cpc', 'https://facebook.com/');
assert.equal(google.referrer, 'Quảng cáo Google (Google Ads)'); assert.equal(google.isFromAd, true);
const custom = visit('https://shop.example/?utm_source=customer_newsletter&fbclid=old', 'https://facebook.com/');
assert.equal(custom.referrer, 'UTM: customer_newsletter'); assert.equal(custom.isFromAd, false);
assert.equal(visit('https://shop.example/?fbclid=organic').referrer, 'Facebook');
assert.equal(visit('https://shop.example/?utm_source=zalo&fbclid=old').referrer, 'Zalo Chat');
assert.equal(visit('https://shop.example/', 'https://other.example/?next=facebook.com').referrer, 'Giới thiệu: other.example');
const beforeExpiry = visit(zaloLink);
clock += 31 * 60 * 1000;
assert.notEqual(visit(zaloLink, '', 'reload').sessionId, beforeExpiry.sessionId);
const otherDomain = visit('https://other-shop.example/');
assert.equal(otherDomain.domain, 'other-shop.example'); assert.equal(otherDomain.referrer, 'Truy cập trực tiếp');
const corrupt = new Map([['crm_attribution', '{bad json']]);
assert.equal(visit('https://shop.example/?ref=google', '', 'navigate', corrupt).referrer, 'Tìm kiếm Google');
const legacy = new Map([['crm_attribution', JSON.stringify({fullUrl: zaloLink, referrer: 'Zalo Chat', utmSource: 'zalo'})]]);
assert.equal(visit('https://shop.example/?ref=facebook', '', 'navigate', legacy).referrer, 'Facebook');
const facebookAdsUrl='https://geminigiare.io.vn/?utm_source=facebook&utm_medium=paid_social&utm_campaign=fb_campaign&fbclid=FB_CLICK';
const facebookAd=visit(facebookAdsUrl,'https://l.facebook.com/');
assert.equal(facebookAd.referrer,'Quảng cáo Facebook (Meta Ads)');
assert.equal(facebookAd.domain,'geminigiare.io.vn');
assert.equal(facebookAd.isFromAd,true);
const hostingZalo='https://old-host.example/?utm_source=zalo&utm_medium=zalo';
const freshMain=visit('https://geminigiare.io.vn/','', 'navigate',new Map([['crm_attribution', JSON.stringify({...zalo,fullUrl:hostingZalo})]]));
assert.equal(freshMain.fullUrl,'https://geminigiare.io.vn/');
assert.equal(freshMain.utmSource,'');
assert.equal(freshMain.referrer,'Truy cập trực tiếp');
const changedInPage=visit(zaloLink,'','navigate',new Map(),ctx=> {
 vm.runInContext("visitorData.ip='203.0.113.8'; visitorData.location='Test city';",ctx);
 ctx.window.location=new URL(facebookAdsUrl);
});
assert.equal(changedInPage.fullUrl,facebookAdsUrl);
assert.equal(changedInPage.referrer,'Quảng cáo Facebook (Meta Ads)');
assert.equal(changedInPage.domain,'geminigiare.io.vn');
assert.equal(changedInPage.ip,'203.0.113.8');
assert.equal(changedInPage.location,'Test city');
for (const name of ['admin.html', 'admin/index.html']) {
  const admin = fs.readFileSync(name, 'utf8');
  const start = admin.indexOf('    function trafficChannel(');
  const end = admin.indexOf('    function setTrafficDays(', start);
  const visits = [
    {referrer: 'Facebook', domain: 'shop.example'},
    {referrer: 'Zalo Chat', domain: 'shop.example'},
    {referrer: 'Giới thiệu: example.com', domain: 'shop.example'},
    {referrer: 'UTM: newsletter', domain: 'shop.example'},
    {referrer: 'Truy cập trực tiếp', domain: 'shop.example'},
    {referrer: 'X (Twitter)', domain: 'other-shop.example'}
  ];
  const ctx = {getVisits: () => visits, currentTrafficDays: 7, currentDomainFilter: 'shop.example', extractDomain: v => v.domain};
  vm.createContext(ctx);
  vm.runInContext(admin.slice(admin.indexOf('    function extractOrderDate('), admin.indexOf('    function renderDailySalesStats(')), ctx);
  vm.runInContext(admin.slice(start, end), ctx);
  const counts = Object.fromEntries(ctx.calculateTrafficSources().map(c => [c.key, c.count]));
  assert.equal(counts.FACEBOOK, 1); assert.equal(counts.ZALO, 1);
  assert.equal(counts.OTHER, 2); assert.equal(counts.DIRECT, 1); assert.equal(counts.X, 0);
  assert.equal(ctx.trafficChannel('Tìm kiếm & Research'), 'RESEARCH');
  assert.equal(ctx.trafficChannel('Khác'), 'OTHER');
  assert.equal(ctx.trafficChannel('Giới thiệu: example.com'), 'OTHER');
  const elements = new Map();
  visits.forEach(v => v.time = new Date().toLocaleDateString('vi-VN'));
  Object.assign(ctx, {getOrders: () => [], serverVisitsData: {totalVisits: 999, todayVisits: 777},
    document: {getElementById: key => {if (!elements.has(key)) elements.set(key, {}); return elements.get(key);}},
    renderDomainFilterBar() {}, renderTrafficSources() {}, renderDailyTrafficTable() {}, renderTrafficDetailedTable() {}});
  const renderStart = admin.indexOf('    function renderTraffic() {');
  const renderEnd = admin.indexOf('\n    function ', renderStart + 10);
  vm.runInContext(admin.slice(renderStart, renderEnd), ctx);
  ctx.renderTraffic();
  assert.equal(elements.get('todayCardVisits').innerText, '5', 'filtered domain must not display global today total');
  assert.equal(elements.get('kpiVisits').innerText, '5', 'filtered domain must not display global lifetime total');
  ctx.currentDomainFilter = 'ALL'; ctx.renderTraffic();
  assert.equal(elements.get('todayCardVisits').innerText, '777');
  assert.equal(elements.get('kpiVisits').innerText, '999');
}
console.log('PASS attribution: changing links, ref/source-only, clean direct entry, reload, expiry, explicit-source priority, frozen domains, corrupt/legacy cache, admin channel counts');
