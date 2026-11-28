const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const dir=path.join(__dirname,'../extension');
const C=require(path.join(dir,'core.js'));
const url='https://p-bandai.com/us/item/N2897694002';
const target={url,title:'ONE PIECE CARD GAME Test',maxPrice:7000,tabId:7,status:'armed',attempts:0,nextAt:0};
const snapshot={url,title:target.title,price:7000,quantity:'1',ready:true,waiting:false,login:false,blocked:false};
function worker(initial=target) {
  let state=structuredClone(initial),listener,removed;
  const effects=[];
  const chrome={
    storage:{local:{get:async()=>({target:structuredClone(state)}),set:async({target:t})=>{state=structuredClone(t);}}},
    runtime:{getURL:p=>'chrome-extension://test/'+p,onMessage:{addListener:f=>listener=f}},
    tabs:{get:async id=>({id,url}),sendMessage:async()=>snapshot,update:async(id,opts)=>effects.push({id,...opts}),onRemoved:{addListener:f=>removed=f}},
    notifications:{create:async msg=>effects.push(msg)},action:{setBadgeText:async msg=>effects.push(msg)}
  };
  vm.runInNewContext(fs.readFileSync(path.join(dir,'background.js'),'utf8'),{chrome,BandaiCart:C,importScripts:()=>{},URL,Date,Promise,Number,String,Error});
  const send=(m,id=7,page=url)=>new Promise(resolve=>listener(m,{tab:{id,url:page}},resolve));
  const popup=m=>new Promise(resolve=>listener(m,{url:'chrome-extension://test/popup.html'},resolve));
  return {send,popup,state:()=>state,effects,close:id=>removed(id)};
}
test('URL whitelist rejects external, checkout, credentials, ports, and deceptive hostnames',()=>{
  for(const value of ['https://evil.com/us/item/X','https://p-bandai.com.evil/us/item/X','http://p-bandai.com/us/item/X','https://p-bandai.com/us/cart','https://a@p-bandai.com/us/item/X','https://p-bandai.com:444/us/item/X']) assert.equal(C.productUrl(value),null);
  assert.equal(C.productUrl(url+'/?x=1#hi'),url);
});
test('price parser handles site zero-width currency and thousands, rejects unknown currency',()=>{
  assert.equal(C.price('US$‌70.00'),7000);assert.equal(C.price('US$ 1,100.00'),110000);
  assert.equal(C.price('$70.00'),null);assert.equal(C.price('70 EUR'),null);
});
test('price, identity, session, quantity and block guards',()=>{
  assert.equal(C.decision(snapshot,target),'click');
  for(const [change,expected] of [[{price:7001},'price'],[{title:'Other'},'unknown'],[{login:true},'login'],[{quantity:'2'},'quantity'],[{blocked:true},'blocked'],[{url:url+'X'},'wrong-page']]) assert.equal(C.decision({...snapshot,...change},target),expected);
  assert.equal(C.decision({...snapshot,ready:false,waiting:true},target),'wait');
  assert.equal(C.decision({...snapshot,ready:false},target),'unknown');
});
test('only a fresh explicit stock refusal permits retry',()=>{
  const message='Could not add the item to your cart because it is out of stock.';
  assert.equal(C.outcome([message],[]),'retry');
  assert.equal(C.outcome([message],[message]),'unknown');
  for(const text of ['OUT OF STOCK','Something went wrong','Request timed out','Added to cart']) assert.equal(C.outcome([text],[]),'unknown');
  assert.equal(C.outcome(['Too many requests'],[]),'blocked');
});
test('concurrent claims produce exactly one click authorization, including duplicate tabs',async()=>{
  const w=worker();const replies=await Promise.all([w.send({type:'claim',snapshot}),w.send({type:'claim',snapshot}),w.send({type:'claim',snapshot},8)]);
  assert.equal(replies.filter(r=>r.ok).length,1);assert.equal(w.state().attempts,1);assert.equal(w.state().status,'awaiting');
});
test('explicit stock failure rearms with cooldown and rejects immediate retry',async()=>{
  const w=worker();await w.send({type:'claim',snapshot});
  assert.equal((await w.send({type:'retry',messages:['Could not add the item to your cart because it is out of stock.'],baseline:[]})).ok,true);
  assert.equal(w.state().status,'armed');assert.ok(w.state().nextAt>Date.now()+4000);
  assert.equal((await w.send({type:'claim',snapshot})).ok,false);
});
test('timeouts and generic errors never rearm an uncertain attempt',async()=>{
  const w=worker();await w.send({type:'claim',snapshot});
  assert.equal((await w.send({type:'retry',messages:['Something went wrong'],baseline:[]})).ok,false);
  assert.equal(w.state().status,'awaiting');
  await w.send({type:'check-cart'});assert.equal(w.state().status,'checking');
  assert.ok(w.effects.some(e=>e.url==='https://p-bandai.com/us/cart'));
});
test('restored in-flight state cannot generate a second claim',async()=>{
  const w=worker({...target,status:'awaiting',attempts:1});
  assert.equal((await w.send({type:'claim',snapshot})).ok,false);
});
test('success requires cart verification from watched tab and matching product',async()=>{
  const w=worker({...target,status:'checking'});
  assert.equal((await w.send({type:'found',productUrl:url},8,'https://p-bandai.com/us/cart')).ok,false);
  assert.equal((await w.send({type:'found',productUrl:url})).ok,false);
  assert.equal((await w.send({type:'found',productUrl:url},7,'https://p-bandai.com/us/cart')).ok,true);
  assert.equal(w.state().status,'done');assert.equal((await w.send({type:'claim',snapshot})).ok,false);
});
test('manual stop prevents new claims and old result cannot rearm',async()=>{
  const w=worker();await w.popup({type:'stop'});
  assert.equal((await w.send({type:'claim',snapshot})).ok,false);
  assert.equal((await w.send({type:'retry',messages:['Could not add the item to your cart because it is out of stock.'],baseline:[]})).ok,false);
});
test('popup arming rejects a second active watcher and too-low price',async()=>{
  const w=worker();assert.match((await w.popup({type:'arm',tabId:7,maxPrice:7000})).error,/Arrête/);
  const p=worker(null);assert.match((await p.popup({type:'arm',tabId:7,maxPrice:6999})).error,/plafond/);
  assert.equal((await p.popup({type:'arm',tabId:7,maxPrice:7000})).target.status,'armed');
});
test('cart pages do not receive any click authorization',async()=>{
  const w=worker();assert.equal((await w.send({type:'claim',snapshot},7,'https://p-bandai.com/us/cart')).ok,false);
});
