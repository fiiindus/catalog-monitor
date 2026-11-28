/* Pure rules shared by the extension and its offline tests. */
(function (root) {
  const clean = s => String(s || '').replace(/[\u200b-\u200d\ufeff]/g, '').replace(/\s+/g, ' ').trim();
  function productUrl(value) {
    try {
      const u = new URL(value);
      if (u.protocol !== 'https:' || u.hostname !== 'p-bandai.com' || u.port || u.username || u.password || !/^\/us\/item\/[A-Za-z0-9]+\/?$/.test(u.pathname)) return null;
      return u.origin + u.pathname.replace(/\/$/, '');
    } catch { return null; }
  }
  function price(value) {
    const m = clean(value).match(/^US\$\s*([\d,]+\.\d{2})$/);
    return m ? Math.round(Number(m[1].replaceAll(',', '')) * 100) : null;
  }
  function decision(snapshot, target) {
    if (productUrl(snapshot.url) !== target.url) return 'wrong-page';
    if (snapshot.blocked) return 'blocked';
    if (snapshot.login) return 'login';
    if (clean(snapshot.title) !== target.title || snapshot.price === null) return 'unknown';
    if (snapshot.price > target.maxPrice) return 'price';
    if (snapshot.quantity !== '1') return 'quantity';
    if (snapshot.ready) return 'click';
    if (snapshot.waiting) return 'wait';
    return 'unknown';
  }
  // Only a NEW explicit refusal can rearm an already sent add request.
  // Generic errors, timeouts, and an unchanged SOLD OUT badge cannot.
  function outcome(messages, baseline) {
    const fresh = messages.map(clean).filter(t => !baseline.includes(t));
    if (fresh.some(t => /captcha|verify (?:that )?you are human|access denied|too many requests|unusual traffic|automated (?:access|traffic)/i.test(t))) return 'blocked';
    if (fresh.some(t => /(?:could not|cannot|unable to|couldn't|failed to) add (?:this |the |an )?(?:item|product).*?(?:cart|basket).*?(?:out of stock|sold out|insufficient stock)|(?:out of stock|sold out|insufficient stock).*?(?:could not|cannot|unable to|failed to) add/i.test(t))) return 'retry';
    return 'unknown';
  }
  const api = {clean, productUrl, price, decision, outcome};
  root.BandaiCart = api;
  if (typeof module !== 'undefined') module.exports = api;
})(globalThis);
