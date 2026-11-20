importScripts('core.js');
// Serialize claims across tabs. An in-flight claim is written before any click.
let queue = Promise.resolve();
const read = async () => (await chrome.storage.local.get('target')).target;
const save = target => chrome.storage.local.set({target});
async function notify(text) {
  try {
    await chrome.notifications.create({type:'basic', iconUrl:'icon.png', title:'Panier Premium Bandai', message:text});
  } catch { /* Popup status and tab focus remain available when OS notifications are disabled. */ }
}
async function handle(m, sender) {
  let t = await read();
  const fromPopup = !sender.tab && sender.url === chrome.runtime.getURL('popup.html');
  if (m.type === 'get') return {target:t};
  if (m.type === 'arm' && fromPopup) {
    const tab = await chrome.tabs.get(m.tabId);
    if (!BandaiCart.productUrl(tab.url)) throw Error('Ouvre une fiche produit Premium Bandai US.');
    const s = await chrome.tabs.sendMessage(tab.id, {type:'inspect'});
    if (s.login || s.blocked || !s.title || s.price === null || s.quantity !== '1') throw Error('Connecte-toi, attends le chargement et laisse la quantité à 1.');
    const maxPrice = Number(m.maxPrice);
    if (!Number.isSafeInteger(maxPrice) || maxPrice < s.price || maxPrice <= 0) throw Error('Le plafond doit couvrir le prix affiché.');
    if (t && ['armed','awaiting','checking'].includes(t.status)) throw Error('Arrête le suivi actuel avant de changer de produit.');
    t = {url:BandaiCart.productUrl(tab.url), title:BandaiCart.clean(s.title), maxPrice, tabId:tab.id,
      status:'armed', attempts:0, nextAt:0, message:'Surveillance active — quantité 1', updatedAt:Date.now()};
    await save(t);
    await chrome.tabs.sendMessage(tab.id, {type:'wake'});
    return {target:t};
  }
  if (m.type === 'stop' && fromPopup) {
    if(t) {t.status='paused';t.message='Arrêté manuellement';await save(t);}
    return {target:t};
  }
  if (!t || sender.tab?.id !== t.tabId) return {ok:false};
  const url = BandaiCart.productUrl(sender.tab.url);
  if (m.type === 'claim') {
    if (t.status !== 'armed' || Date.now() < t.nextAt || url !== t.url || BandaiCart.decision(m.snapshot,t) !== 'click') return {ok:false};
    t.status='awaiting';t.attempts++;t.updatedAt=Date.now();t.message=`Tentative ${t.attempts} en cours`;
    await save(t);return {ok:true};
  }
  if (m.type === 'retry' && t.status === 'awaiting' && url === t.url && BandaiCart.outcome(m.messages || [], m.baseline || []) === 'retry') {
    t.status='armed';t.nextAt=Date.now()+5000;t.message='Rupture confirmée : nouvelle tentative dans 5 s';await save(t);return {ok:true};
  }
  if (m.type === 'check-cart' && t.status === 'awaiting' && url === t.url) {
    t.status='checking';t.message='Vérification du panier après la tentative';await save(t);
    await chrome.tabs.update(t.tabId,{url:'https://p-bandai.com/us/cart',active:true});return {ok:true};
  }
  if (m.type === 'found' && t.status === 'checking' && new URL(sender.tab.url).pathname === '/us/cart' && m.productUrl === t.url) {
    t.status='done';t.message='Article repéré dans le panier — vérifie quantité et prix, puis paie';await save(t);
    await chrome.action.setBadgeText({text:'OK'});await notify(t.message);return {ok:true};
  }
  if (m.type === 'pause' && ['armed','awaiting','checking'].includes(t.status)) {
    t.status='paused';t.message=String(m.reason || 'Vérification manuelle nécessaire').slice(0,200);await save(t);
    await chrome.action.setBadgeText({text:'!'});await chrome.tabs.update(t.tabId,{active:true});await notify(t.message);return {ok:true};
  }
  return {ok:false};
}
chrome.runtime.onMessage.addListener((message,sender,respond) => {
  const task = queue.then(() => handle(message,sender));
  queue = task.catch(() => {});
  task.then(respond,error=>respond({error:error.message}));return true;
});
chrome.tabs.onRemoved.addListener(tabId => {
  queue = queue.then(async()=>{const t=await read();if(t?.tabId===tabId && ['armed','awaiting','checking'].includes(t.status)) {t.status='paused';t.message='Onglet fermé : suivi arrêté';await save(t);}}).catch(()=>{});
});
