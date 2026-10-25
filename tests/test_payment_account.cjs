const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function extract(html, name) {
  const start = html.indexOf('    function ' + name + '(');
  assert.ok(start >= 0, name);
  const tail = html.slice(start);
  const next = tail.slice(5).search(/^    (?:async )?function /m);
  return next < 0 ? tail : tail.slice(0, next + 5);
}
const expected = {bankPublicId:'cmvkpk77d128c01p4f27u9qy5',vaNumber:'V1T61023152838',accountNo:'V1T61023152838',physicalAccountNo:'8809642706',bankBin:'970418',accountName:'NGO ANH KHOI',bankCode:'BIDV'};
for (const filename of ['index.html','admin.html','admin/index.html']) {
  const html = fs.readFileSync(filename,'utf8');
  const cache = {bankPublicId:'cmv2nmvn408tb01mny26u27ie', accountNo:'VQRQAMRMQ5816', bankBin:'970422', accountName:'NGUYEN TRAN HAN', packagePrice:139000, enabled:false, apiKey:'cached-test'};
  const saved = new Map([['crm_payment_api_config',JSON.stringify(cache)]]);
  const ctx = {CONFIG:expected,localStorage:{getItem:k=>saved.get(k)||null,setItem:(k,v)=>saved.set(k,v)},syncPaymentUI(){},syncPricingUI(){},adminApiFetch(){}};
  vm.createContext(ctx);
  vm.runInContext(extract(html,'migrateWeb1PaymentConfig'),ctx);
  if (filename==='index.html') {
    vm.runInContext(extract(html,'getPaymentApiConfig'),ctx);
    const cfg=ctx.getPaymentApiConfig();
    for (const [key,value] of Object.entries(expected)) assert.equal(cfg[key],value,filename+' '+key);
    assert.equal(cfg.packagePrice,139000); assert.equal(cfg.enabled,false);
    const configSource=html.match(/    const CONFIG = \{[\s\S]*?\n    \};/)[0];
    const cfgActual=vm.runInNewContext(configSource+'\nCONFIG');
    for (const key of ['accountNo','physicalAccountNo','bankBin','accountName']) assert.equal(cfgActual[key],expected[key]);
    assert.ok(!/<img id="modalQrImage"[^>]*src="data:/.test(html),'old embedded QR removed');
  } else {
    vm.runInContext(extract(html,'getPaymentConfig'),ctx);
    vm.runInContext(extract(html,'savePaymentConfig'),ctx);
    const cfg=ctx.getPaymentConfig();
    for (const [key,value] of Object.entries(expected)) assert.equal(cfg[key],value,filename+' '+key);
    assert.equal(cfg.packagePrice,139000); assert.equal(cfg.enabled,false);
    ctx.savePaymentConfig(cache);
    const persisted=JSON.parse(saved.get('crm_payment_api_config'));
    for (const [key,value] of Object.entries(expected)) assert.equal(persisted[key],value);
    saved.delete('crm_payment_api_config');
    const defaults=ctx.getPaymentConfig();
    for (const [key,value] of Object.entries(expected)) assert.equal(defaults[key],value);
  }
}
const config=JSON.parse(fs.readFileSync('payment_config.json','utf8'));
for (const [key,value] of Object.entries(expected)) assert.equal(config[key],value);
console.log('PASS Web1 BIDV account: checkout, admin defaults, legacy cache migration, persisted config, and embedded QR removal');
