(() => {
  const C = BandaiCart;
  const started = Date.now();
  let busy=false, reloadTimer=null, awaitingSince=0, baseline=[];
  const send = message => chrome.runtime.sendMessage(message);
  const visible = el => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  function messages() {
    return Array.from(document.querySelectorAll('[role="alert"], [role="dialog"], [aria-modal="true"], dialog[open]'))
      .filter(visible).map(n=>C.clean(n.innerText)).filter(Boolean);
  }
  function snapshot() {
    const box=document.querySelector('.o-items__sidebar--inner');
    const buttons=Array.from(box?.querySelectorAll('button') || []).filter(visible);
    // msg.placeOrder was inspected on the product page; never use a checkout button.
    const candidates=buttons.filter(b=>b.dataset.bsTextKey==='msg.placeOrder' || /^ADD TO CART$/i.test(C.clean(b.innerText)));
    const btn=candidates.length===1 ? candidates[0] : null;
    const flags=C.clean(box?.querySelector('.o-items__sidebar-flag')?.innerText);
    const pageText=C.clean(document.body.innerText);
    return {url:location.href, title:C.clean(box?.querySelector('h1')?.textContent),
      price:C.price(box?.querySelector('.o-items__sidebar-price-currency p')?.textContent),
      quantity:C.clean(box?.querySelector('.c-input-quantity__num')?.textContent),
      login:Array.from(document.querySelectorAll('a[href*="/us/login"]')).some(visible),
      blocked:/verify (?:that )?you are human|access denied|too many requests|unusual traffic|automated (?:access|traffic)/i.test(pageText) || !!document.querySelector('iframe[src*="captcha"], iframe[src*="challenges.cloudflare.com"]'),
      ready:!!btn && !btn.disabled && btn.getAttribute('aria-disabled')!=='true' && !btn.classList.contains('is-noActive'),
      waiting:/OUT OF STOCK|SOLD OUT|COMING SOON|PRE-ORDER CLOSED/i.test(flags+' '+buttons.map(b=>b.innerText).join(' ')), btn};
  }
  function publicSnapshot() {const {btn,...s}=snapshot();return s;}
  function scheduleReload(delay=5000) {
    if(reloadTimer) return;
    reloadTimer=setTimeout(async()=>{
      reloadTimer=null;
      const {target:t}=await send({type:'get'});
      if(t?.status==='armed' && t.url===C.productUrl(location.href)) location.reload();
    },delay);
  }
  async function tick() {
    if(busy) return;busy=true;
    try {
      const {target:t}=await send({type:'get'});
      if(!t || !['armed','awaiting','checking'].includes(t.status)) return;
      if(t.status==='checking') {
        if(location.pathname!=='/us/cart') return;
        // Recommendations may link to the same item: require a real quantity
        // control in a small ancestor containing no other product identity.
        const link=Array.from(document.querySelectorAll('a[href]')).find(a=>{
          if(!visible(a) || C.productUrl(a.href)!==t.url) return false;
          let row=a.parentElement;
          for(let depth=0;row && depth<5 && !['MAIN','BODY','HTML'].includes(row.tagName);depth++,row=row.parentElement) {
            const quantity=row.querySelector('.c-input-quantity__num');
            const products=Array.from(row.querySelectorAll('a[href]')).map(x=>C.productUrl(x.href)).filter(Boolean);
            if(quantity && C.clean(quantity.textContent)==='1' && products.length && products.every(u=>u===t.url)) return true;
          }
          return false;
        });
        if(link) await send({type:'found',productUrl:t.url});
        else if(Date.now()-started>20000) await send({type:'pause',reason:'Ajout non confirmé : vérifie le panier avant de relancer.'});
        return;
      }
      if(C.productUrl(location.href)!==t.url) return;
      const s=publicSnapshot();
      if(s.blocked) {await send({type:'pause',reason:'Vérification ou blocage du site : suivi arrêté.'});return;}
      if(t.status==='awaiting') {
        // After a reload/crash, never repeat an in-flight request blindly.
        if(!awaitingSince) {await send({type:'check-cart'});return;}
        const current=messages();const outcome=C.outcome(current,baseline);
        if(outcome==='blocked') await send({type:'pause',reason:'Accès refusé par le site : suivi arrêté.'});
        else if(outcome==='retry') {
          const r=await send({type:'retry',messages:current,baseline});
          if(r.ok) {awaitingSince=0;scheduleReload(5000);}
        } else if(Date.now()-awaitingSince>15000) await send({type:'check-cart'});
        return;
      }
      const action=C.decision(s,t);
      if(action==='wait') {scheduleReload(Math.max(5000,t.nextAt-Date.now()));return;}
      if(action==='unknown') {
        if(Date.now()-started>20000) await send({type:'pause',reason:'Fiche non reconnue : contrôle manuel nécessaire.'});
        return;
      }
      if(action!=='click') {await send({type:'pause',reason:({login:'Session déconnectée : reconnecte-toi puis relance.',price:'Prix supérieur au plafond : suivi arrêté.',quantity:'La quantité doit rester à 1.'})[action] || 'Page inattendue'});return;}
      if(Date.now()<t.nextAt) return;
      baseline=messages();
      const r=await send({type:'claim',snapshot:s});
      if(!r.ok) return;
      awaitingSince=Date.now();
      // Revalidate after the async claim. If anything changed, pause, never click a new button.
      const fresh=snapshot();
      if(C.decision(fresh,t)!=='click') {await send({type:'pause',reason:'Fiche modifiée pendant la tentative : vérifie le panier.'});return;}
      fresh.btn.click();
    } catch { /* No network/extension failure can cause an unacknowledged retry. */ }
    finally {busy=false;}
  }
  chrome.runtime.onMessage.addListener((m,sender,respond)=>{
    if(m.type==='inspect') {respond(publicSnapshot());return;}
    if(m.type==='wake') {tick();respond({ok:true});}
  });
  // DOM changes are cheap checks; only a recognized waiting state triggers a reload.
  let debounce;
  new MutationObserver(()=>{clearTimeout(debounce);debounce=setTimeout(tick,100);}).observe(document.documentElement,{subtree:true,childList:true,attributes:true});
  setInterval(tick,1000);tick();
})();
