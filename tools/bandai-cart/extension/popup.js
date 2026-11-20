const $=id=>document.getElementById(id);
let tabId;
async function refresh() {
  const {target:t}=await chrome.runtime.sendMessage({type:'get'});
  $('status').textContent=t ? `${t.message} · ${t.attempts} tentative(s)` : 'Aucun suivi actif.';
}
(async()=>{
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});tabId=tab?.id;
  try {
    if(!BandaiCart.productUrl(tab?.url)) throw Error('Ouvre une fiche Premium Bandai US.');
    const s=await chrome.tabs.sendMessage(tabId,{type:'inspect'});
    $('product').textContent=s.title || 'Attends le chargement de la fiche.';
    if(s.price!==null) $('price').value=(s.price/100).toFixed(2);
  } catch(e) {$('product').textContent=e.message;$('arm').disabled=true;}
  await refresh();
})();
$('arm').onclick=async()=>{
  if(!$('checked').checked) {$('status').textContent='Vérifie d’abord le panier et coche la case.';return;}
  const r=await chrome.runtime.sendMessage({type:'arm',tabId,maxPrice:Math.round(Number($('price').value)*100)});
  if(r.error) $('status').textContent=r.error;else await refresh();
};
$('stop').onclick=async()=>{await chrome.runtime.sendMessage({type:'stop'});await refresh();};
chrome.storage.onChanged.addListener(refresh);
