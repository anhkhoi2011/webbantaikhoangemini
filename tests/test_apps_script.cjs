const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
function environment() {
  const sheets = new Map(), sends = [], emails = [], edits = [];
  let failedChat = '';
  let providerPayments = [];
  class Range {
    constructor(sheet, r, c, nr=1, nc=1) { Object.assign(this,{sheet,r,c,nr,nc}); }
    getValues() { return Array.from({length:this.nr}, (_,r)=>Array.from({length:this.nc},(_,c)=>(this.sheet.rows[this.r+r-1]||[])[this.c+c-1] ?? '')); }
    getValue() { return this.getValues()[0][0]; }
    setValues(values) { values.forEach((row,i)=>row.forEach((value,j)=>{ const r=this.r+i-1; this.sheet.rows[r] ||= []; this.sheet.rows[r][this.c+j-1]=value; }));return this; }
    setValue(value) { return this.setValues([[value]]); }
  }
  for(const method of ['setBackground','setFontColor','setFontWeight','setFontSize','setHorizontalAlignment','setVerticalAlignment']) Range.prototype[method]=function(){return this;};
  class Sheet {
    constructor(name) { this.name=name;this.rows=[];this.cols=26; }
    getName(){return this.name;}
    setName(name){sheets.delete(this.name);this.name=name;sheets.set(name,this);return this;}
    getLastRow(){return this.rows.length;}
    getLastColumn(){return Math.max(0,...this.rows.map(r=>r.length));}
    getMaxColumns(){return this.cols;}
    insertColumnsAfter(_,n){this.cols+=n;}
    getRange(...args){return new Range(this,...args);}
    getDataRange(){return this.getRange(1,1,this.getLastRow(),this.getLastColumn());}
    appendRow(row){this.rows.push([...row]);return this;}
    insertRowBefore(r){this.rows.splice(r-1,0,[]);}
    setFrozenRows(){} setRowHeight(){} setColumnWidth(){}
  }
  const ss={getSheetByName:name=>sheets.get(name),getSheets:()=>[...sheets.values()],insertSheet(name){const sheet=new Sheet(name);sheets.set(name,sheet);return sheet;}};
  let locked=false;
  const ctx={console, Date, Logger:{log(){}}, ContentService:{MimeType:{JSON:'json'}, createTextOutput(text){return {text,setMimeType(){return this;}};}},
    LockService:{getScriptLock(){return {waitLock(){assert.equal(locked,false);locked=true;},hasLock:()=>locked,releaseLock(){locked=false;}};}},
    SpreadsheetApp:{openById:()=>ss,getActiveSpreadsheet:()=>ss,flush(){}},
    Utilities:{DigestAlgorithm:{SHA_256:'sha256'},computeDigest:(_,seed)=>[...crypto.createHash('sha256').update(seed).digest()],formatDate:date=>new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Bangkok',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(date).replace(',', ''),base64Encode:v=>Buffer.from(v).toString('base64')},
    GmailApp:{sendEmail(...args){emails.push(args);}},
    UrlFetchApp:{fetch(url,opts){if(opts.method==='get')return {getContentText:()=>JSON.stringify({data:{data:providerPayments}})};const payload=JSON.parse(opts.payload);(url.endsWith('/editMessageText')?edits:sends).push(payload);return {getContentText:()=>JSON.stringify(payload.chat_id===failedChat?{ok:false,description:'retry'}:{ok:true,result:{message_id:payload.message_id || sends.length}})};}}
  };
  vm.createContext(ctx);vm.runInContext(fs.readFileSync('GoogleAppsScript_CRM_AutoBot.js','utf8'),ctx);
  return {ctx,sheets,sends,edits,emails,payments:rows=>providerPayments=rows,fail:cid=>failedChat=cid,post:data=>JSON.parse(ctx.doPost({postData:{contents:JSON.stringify(data)}}).text)};
}
const base={orderId:'#TEST-A',amount:90000,amountRaw:90000,name:'Khách <test>',phone:'0900000000',email:'test@example.invalid',memo:'PRO18T 0900000000 AABBCCDD',referrer:'Facebook',utmSource:'facebook',utmMedium:'cpc',utmCampaign:'Campaign',utmContent:'Ad A',utmTerm:'keyword',fbclid:'click',gclid:'google',ttclid:'tiktok',ip:'203.0.113.5',location:'Test city',device:'Mobile',browser:'Safari',fullUrl:'https://example.invalid/?utm_source=facebook',domain:'example.invalid',createdAt:'2026-10-23T05:00:00Z',status:'Đã thanh toán (Chờ cấp link)',paymentTxId:'BANK-1'};
{
 const e=environment();
 for(let i=0;i<4;i++) assert.equal(e.post({...base,action:'new_order'}).status,'success');
 assert.equal(e.sheets.has('GIAO_DICH'),false,'new_order must never become a raw bank event');
 assert.equal(e.sheets.get('DON_HANG').rows.length,2);
 assert.equal(e.sends.length,2,'one notification per chat');
 assert.deepEqual(e.sends.map(x=>x.chat_id),['-1004413665683','-5585627393']);
 assert.ok(e.sends[0].text.includes('203.0.113.5'));
 assert.ok(e.sends[0].text.includes('Khách &lt;test&gt;'));
 const row=e.sheets.get('DON_HANG').rows[1];
 assert.equal(row[18],'Safari');assert.equal(row[22],'cpc');assert.equal(row[29],'BANK-1');
 e.post({...base,action:'sync_order',name:'Updated'});assert.equal(e.sends.length,2);
 e.post({...base,action:'pending_order',status:'Chờ thanh toán'});assert.equal(e.sheets.get('DON_HANG').rows[1][11],base.status,'late pending must not downgrade paid');
}
{
 const e=environment();e.fail('-5585627393');
 assert.equal(e.post({...base,action:'new_order'}).notificationsComplete,false);
 e.fail('');assert.equal(e.post({...base,action:'new_order'}).notificationsComplete,true);
 assert.deepEqual(e.sends.map(x=>x.chat_id),['-1004413665683','-5585627393','-5585627393']);
}
{
 const e=environment();
 e.post({...base,action:'pending_order',status:'Chờ thanh toán',paymentTxId:''});
 for(let i=0;i<4;i++) e.post({id:'delivery-'+i,amount:90000,content:'QAMRMQ5816 '+base.memo,status:'COMPLETED',time:'2026-10-23T05:01:00Z'});
 assert.equal(e.sheets.get('GIAO_DICH').rows.length,2,'delivery UUID must not create another transaction');
 assert.equal(e.sheets.get('DON_HANG').rows.length,2);
 assert.equal(e.sends.length,2);
 assert.ok(e.sheets.get('DON_HANG').rows[1][11].startsWith('Đã thanh toán'));
}
{
 const e=environment(); e.post({id:'unmatched',amount:90000,content:'OTHER',status:'COMPLETED'});
 assert.notEqual(e.sheets.get('DON_HANG'),e.sheets.get('GIAO_DICH'));
 assert.equal(e.sends.length,0,'unmatched bank transaction must not become a customer order');
 e.post({...base,action:'pending_order',status:'Chờ thanh toán',paymentTxId:''});
 e.post({amount:90000,content:base.memo,status:'PENDING'});assert.equal(e.sends.length,0);
 e.post({amount:90000,content:base.memo,status:'COMPLETED',transferType:'out'});assert.equal(e.sends.length,0);
}
{
 const e=environment();
 e.post({id:'early-bank',amount:'90000.00',content:base.memo,status:'COMPLETED'});
 e.post({...base,action:'pending_order',status:'Chờ thanh toán',paymentTxId:''});
 assert.equal(e.sends.length,2,'payment before pending_order must reconcile once');
 const before=e.sheets.get('DON_HANG').rows[1][4];
 const result=e.post({...base,action:'new_order',orderId:'#OTHER',paymentTxId:'early-bank',name:'Wrong customer'});
 assert.equal(result.status,'error');assert.equal(e.sheets.get('DON_HANG').rows[1][4],before);
 assert.equal(JSON.parse(e.ctx.doGet({parameter:{action:'health'}}).text).columns,40);
 assert.equal(JSON.parse(e.ctx.doGet({parameter:{action:'health'}}).text).build,'2026-10-23-source-lock');
 assert.equal(e.ctx.money_(90000.0),90000);assert.equal(e.ctx.money_('90.000đ'),90000);assert.equal(e.ctx.money_('-90000'),-90000);
}
{
 const e=environment();
 const longUrl='https://example.invalid/?utm_source=zalo&utm_medium=zalo&utm_campaign='+('campaign'.repeat(20))+'&utm_content=EXPECTED_END';
 e.post({...base,action:'new_order',fullUrl:longUrl});
 assert.ok(e.sends[0].text.includes('utm_content=EXPECTED_END'),'Telegram must retain an ordinary full campaign URL beyond 90 characters');
 assert.equal(e.sheets.get('DON_HANG').rows[1][19],longUrl);
 const crowded=environment();
 const huge='&'.repeat(3000);
 crowded.post({...base,action:'new_order',fullUrl:huge,name:huge,email:huge,phone:huge,referrer:huge,rawReferrer:huge,location:huge,userAgent:huge,utmCampaign:huge,utmContent:huge,licenseLink:huge});
 assert.ok(crowded.sends[0].text.length<=4000,'oversized metadata must stay within Telegram message budget');
 assert.equal(crowded.sheets.get('DON_HANG').rows[1][19],huge,'Sheet keeps the original full URL');
}
{
 const e=environment();
 const check=amount=>JSON.parse(e.ctx.doGet({parameter:{action:'check_payment',orderId:base.orderId,memo:base.memo,amount}}).text);
 e.payments([{id:'BANK-DECIMAL',status:'PAID',content:base.memo,amount:'69000.00'}]);
 assert.equal(check('90000').paid,false,'decimal amounts must be compared at their actual VND value');
 assert.equal(check('90000.00').paid,false);
 e.payments([{id:'BANK-DECIMAL',status:'PAID',content:base.memo,amount:'90000.00'}]);
 const result=check('90000.00');assert.equal(result.paid,true);assert.equal(result.transaction.amount,90000);
 e.payments([{id:'BANK-ZERO',status:'PAID',content:base.memo,amount:'0.00'}]);
 assert.equal(check('90000').paid,false);assert.equal(check('0').paid,false);
}
{
 const e=environment();
 const facebook={...base, action:'pending_order', paymentTxId:'', status:'Chờ thanh toán',
  fullUrl:'https://geminigiare.io.vn/?utm_source=facebook&utm_medium=paid_social', domain:'geminigiare.io.vn',
  referrer:'Quảng cáo Facebook (Meta Ads)', utmSource:'facebook', utmMedium:'paid_social', utmContent:'', fbclid:'',
  sessionId:'FB-VISIT', landingAt:'2026-10-23T08:25:00Z'};
 e.post(facebook);
 const originalStored=e.ctx.rowToOrder_(e.sheets.get('DON_HANG').rows[1]);
 const stale={...facebook, fullUrl:'https://old-host.example/?utm_source=zalo', domain:'old-host.example',
  referrer:'Zalo Chat', utmSource:'zalo', utmMedium:'zalo', utmContent:'OLD-ZALO-AD', fbclid:'OLD-CLICK', sessionId:'OLD-VISIT',landingAt:'2026-10-22T08:25:00Z'};
 e.post(stale);
 e.post({...stale, action:'new_order', status:'Đã thanh toán (Chờ cấp link)', paymentTxId:'BANK-FB'});
 const stored=e.ctx.rowToOrder_(e.sheets.get('DON_HANG').rows[1]);
 for(const key of ['fullUrl','domain','referrer','utmSource','utmMedium','utmContent','fbclid','sessionId','landingAt']) {
  assert.equal(stored[key],originalStored[key], 'late sync replaced '+key);
 }
 assert.ok(e.sends[0].text.includes('Quảng cáo Facebook'));
 assert.ok(!e.sends[0].text.includes('old-host.example'));
}
{
 const e=environment();
 e.post({...base, action:'new_order'});
 assert.equal(e.sends.length,2);
 assert.equal(e.edits.length,0);
 const issued={...base, action:'new_order', licenseLink:'https://example.invalid/real-issued-link',status:'Đã thanh toán (MBBank)'};
 for(let i=0;i<4;i++) e.post(issued);
 assert.equal(e.sends.length,2,'issuing a link must edit the existing message, not send another order');
 assert.equal(e.edits.length,2,'one successful edit per chat');
 assert.deepEqual(e.edits.map(x=>x.message_id),[1,2]);
 assert.ok(e.edits.every(x=>x.text.includes('real-issued-link')));
 assert.ok(e.edits.every(x=>!x.text.includes('Chờ cấp link')));
}
{
 const e=environment();
 e.post({...base,action:'new_order'});
 e.fail('-5585627393');
 const issued={...base,action:'new_order',licenseLink:'https://example.invalid/link',status:'Đã thanh toán (MBBank)'};
 assert.equal(e.post(issued).notificationsComplete,false);
 e.fail('');
 assert.equal(e.post(issued).notificationsComplete,true);
 assert.equal(e.sends.length,2,'an edit retry must never create a duplicate order notification');
 assert.deepEqual(e.edits.map(x=>x.chat_id),['-1004413665683','-5585627393','-5585627393']);
}
console.log('PASS Apps Script: routing, four retries, changed UUID, row upsert, tracking, two chats, partial failure retry, late pending, unmatched/debit/pending events');
