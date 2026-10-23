const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function extract(text, name) {
  const start=text.indexOf('    function '+name+'(');
  assert.ok(start>=0, name);
  const end=text.indexOf('\n    function ',start+10);
  return text.slice(start,end<0?undefined:end);
}
for(const file of ['admin.html','admin/index.html']) {
 const html=fs.readFileSync(file,'utf8');
 class ClockDate extends Date {constructor(...args){super(...(args.length?args:['2026-10-23T06:00:00Z']));} static now(){return Date.parse('2026-10-23T06:00:00Z');}}
 const orders=[
  {orderId:'paid',status:'Đã thanh toán (Chờ cấp link)',amount:'90.000đ',amountRaw:90000,time:'13:00:00 23/10/2026',paidAt:'2026-10-23T06:00:00Z',domain:'shop.example',referrer:'Zalo Chat'},
  {orderId:'pending',status:'Chờ thanh toán',amount:'90.000đ',amountRaw:90000,time:'13:00:00 23/10/2026',domain:'shop.example',referrer:'Zalo Chat'},
  {orderId:'cancelled',status:'Đã hủy',amount:'90.000đ',amountRaw:90000,time:'13:00:00 23/10/2026',domain:'shop.example',referrer:'Zalo Chat'},
  {orderId:'other-domain',status:'paid',amount:'69000.00',time:'13:00:00 23/10/2026',domain:'other.example',referrer:'Facebook'},
  {orderId:'missing-amount',status:'paid',time:'13:00:00 23/10/2026',domain:'shop.example',referrer:'Zalo Chat'},
  {orderId:'refunded',status:'Đã thanh toán (Hoàn tiền)',amountRaw:90000,time:'13:00:00 23/10/2026',domain:'shop.example',referrer:'Zalo Chat'}
 ];
 const elements=new Map(); const sent=[];
 const ctx={console,Date:ClockDate,getOrders:()=>orders,getVisits:()=>[{time:'13:00:00 23/10/2026',domain:'shop.example',referrer:'Zalo Chat'}],
  getInventory:()=>[],sendTelegramMessage:msg=>sent.push(msg),serverVisitsData:{totalVisits:6,todayVisits:6},currentTrafficDays:1,currentSourceFilter:'ALL',currentDomainFilter:'shop.example',extractDomain:v=>v.domain,
  document:{getElementById:key=>{if(['ordersTableBody','dailyStatsTableBody'].includes(key))return null;if(!elements.has(key))elements.set(key,{});return elements.get(key);},createElement:()=>({})},
  renderDomainFilterBar(){},renderTrafficSources(){},renderDailyTrafficTable(){},renderTrafficDetailedTable(){}};
 vm.createContext(ctx);
 for(const name of ['extractOrderDate','parseAmountToNumber','orderIsPaid','renderDailySalesStats','renderOrders','trafficChannel','renderTraffic','notifyTelegramDailyReport']) vm.runInContext(extract(html,name),ctx);
 assert.equal(ctx.parseAmountToNumber('90000.00'),90000);assert.equal(ctx.parseAmountToNumber('69.000đ'),69000);assert.equal(ctx.parseAmountToNumber(''),0);
 assert.equal(ctx.extractOrderDate('2026-10-22T18:15:00Z'),'23/10/2026');
 assert.equal(ctx.extractOrderDate('1:00:00 1/2/2026'),'01/02/2026');
 assert.equal(ctx.extractOrderDate(''), '');
 ctx.renderOrders();
 assert.equal(elements.get('kpiRevenue').innerText,'159.000đ','only paid orders contribute revenue and absent amounts do not default to 90k');
 assert.equal(elements.get('statsAllTimeRev').innerText,'159.000đ');
 assert.equal(elements.get('statsTodayOrders').innerText,'3 đơn');
 assert.equal(elements.get('kpiOrders').innerText,'6','order list still counts all created orders');
 ctx.renderTraffic();
 assert.equal(elements.get('todayCardOrders').innerText,'2 đơn','paid sales must respect selected domain');
 assert.ok(elements.get('todayCardRevenue').innerHTML.includes('90.000đ'));
 ctx.notifyTelegramDailyReport();
 assert.ok(sent[0].includes('159.000 VNĐ'));assert.ok(sent[0].includes('(3 đơn)'));
 const rows=[];elements.set('dailyTrafficTableBody',{appendChild:row=>rows.push(row)});
 vm.runInContext(extract(html,'renderDailyTrafficTable'),ctx);
 ctx.currentSourceFilter='Facebook';ctx.renderDailyTrafficTable();
 assert.equal(rows.length,1);
 assert.ok(rows[0].innerHTML.includes('0 đơn'),'source filter must apply to paid orders as well as visits');
}
console.log('PASS sales reporting: paid/pending/cancelled/refunded, missing/decimal amounts, domain/source filters and GMT+7 dates');
