const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const C=require('../extension/core.js');
const url='https://p-bandai.com/us/item/N2897694002';
const title='ONE PIECE CARD GAME Test';
async function run(options={}) {
  const sent=[],timers=[];let clicks=0;
  let target={url,title,maxPrice:7000,status:options.status||'armed',nextAt:0};
  const visible=node=>Object.assign({getClientRects:()=>[{}]},node);
  const button=visible({dataset:{bsTextKey:'msg.placeOrder'},innerText:'PLACE ORDER',disabled:false,getAttribute:()=>null,classList:{contains:()=>false},click:()=>clicks++});
  const box={querySelector:s=>({
    'h1':{textContent:title},'.o-items__sidebar-price-currency p':{textContent:'US$‌70.00'},
    '.c-input-quantity__num':{textContent:'1'},'.o-items__sidebar-flag':{innerText:options.waiting?'OUT OF STOCK':'IN STOCK'}
  })[s],querySelectorAll:()=>options.waiting?[]:[button]};
  let interval;
  const document={body:{innerText:''},documentElement:{},querySelector:s=>s==='.o-items__sidebar--inner'?box:null,
    querySelectorAll:s=>s==='a[href*="/us/login"]' && options.login?[visible({})]:s==='a[href]'?(options.cartLinks||[]):[]};
  const chrome={runtime:{sendMessage:async m=>{
    sent.push(m);if(m.type==='get')return {target:structuredClone(target)};
    if(m.type==='claim'){if(target.status!=='armed')return {ok:false};target.status='awaiting';return {ok:true};}
    return {ok:true};},onMessage:{addListener:()=>{}}}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../extension/content.js'),'utf8'),{
    BandaiCart:C,chrome,document,location:{href:options.cart?'https://p-bandai.com/us/cart':url,pathname:options.cart?'/us/cart':'/us/item/N2897694002',reload:()=>{}},
    getComputedStyle:()=>({visibility:'visible'}),MutationObserver:class{observe(){}},
    setInterval:f=>{interval=f;},setTimeout:(f,ms)=>{timers.push({f,ms});return timers.length;},clearTimeout:()=>{},Date
  });
  await new Promise(r=>setImmediate(r));
  return {sent,timers,clicks:()=>clicks,tick:async()=>{interval();await new Promise(r=>setImmediate(r));}};
}
test('actual product sidebar PLACE ORDER is clicked once, never on repeated DOM checks',async()=>{
  const r=await run();assert.equal(r.clicks(),1);await r.tick();await r.tick();assert.equal(r.clicks(),1);
});
test('recognized stock absence schedules a five-second reload without clicking',async()=>{
  const r=await run({waiting:true});assert.equal(r.clicks(),0);assert.equal(r.timers[0].ms,5000);
});
test('visible sign-in stops instead of using an anonymous cart',async()=>{
  const r=await run({login:true});assert.equal(r.clicks(),0);assert.ok(r.sent.some(m=>m.type==='pause'));
});
test('reloaded in-flight attempt requests a cart check, never another add',async()=>{
  const r=await run({status:'awaiting'});assert.equal(r.clicks(),0);assert.ok(r.sent.some(m=>m.type==='check-cart'));
});
test('cart recommendation link cannot be mistaken for a cart line',async()=>{
  const recommendation={href:url,getClientRects:()=>[{}],parentElement:{tagName:'DIV',querySelector:()=>null,querySelectorAll:()=>[],parentElement:null}};
  const r=await run({status:'checking',cart:true,cartLinks:[recommendation]});
  assert.equal(r.clicks(),0);assert.equal(r.sent.some(m=>m.type==='found'),false);
});
test('cart line with product identity and quantity 1 is recognized',async()=>{
  const link={href:url,getClientRects:()=>[{}]};link.parentElement={tagName:'DIV',querySelector:()=>({textContent:'1'}),querySelectorAll:()=>[link],parentElement:null};
  const r=await run({status:'checking',cart:true,cartLinks:[link]});assert.ok(r.sent.some(m=>m.type==='found'));assert.equal(r.clicks(),0);
});
