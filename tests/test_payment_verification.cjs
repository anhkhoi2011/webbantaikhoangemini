const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('index.html','utf8');
const query=html.slice(html.indexOf('    async function queryPaymentApi('),html.indexOf('    async function manualVerifyPaymentClick('));
const order={orderId:'#REAL-CHECK',memo:'PRO18T 0900000000',phone:'0900000000',amountRaw:129000,createdAt:'2026-10-26T05:00:00Z'};
const stored=new Map([['crm_simulated_payment',JSON.stringify({forceAll:true,phone:order.phone,amount:129000})]]);
let providerPaid=false,successes=0,stops=0,checks=0;
const ctx={console,URLSearchParams,currentOrder:order,CONFIG:{amount:129000,googleAppsScriptUrl:''},isPollingCheck:false,completingOrders:new Set(),pollScanCount:0,formatVnd:n=>String(n),localStorage:{getItem:k=>stored.get(k),removeItem:k=>stored.delete(k)},document:{getElementById:()=>null},smartApiFetch:async()=>{checks++;return {ok:true,json:async()=>({paid:providerPaid,transaction:{id:'BANK-VERIFIED',amount:129000}})};},stopPaymentPolling(){stops++;},async triggerPaymentSuccess(tx){assert.equal(tx.id,'BANK-VERIFIED');successes++;}};
vm.createContext(ctx);vm.runInContext(query,ctx);
(async()=>{
 assert.equal(await ctx.checkPaymentRealStatus(),false);
 assert.equal(successes,0);assert.equal(stops,0);assert.equal(checks,1);
 assert.equal(stored.has('crm_simulated_payment'),false,'stale forceAll sandbox state is discarded');
 providerPaid='false';assert.equal(await ctx.checkPaymentRealStatus(),false);assert.equal(successes,0,'only a boolean true confirms payment');
 providerPaid=true;assert.equal(await ctx.checkPaymentRealStatus(),true);assert.equal(successes,1);assert.equal(stops,1);
 console.log('PASS live verification: sandbox cannot confirm, unpaid waits, boolean paid response triggers success');
})().catch(e=>{console.error(e);process.exitCode=1;});
