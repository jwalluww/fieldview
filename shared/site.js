// FieldView shared site chrome: small-screen notice + trademark/credits footer.
// Included on every page with:  <script src="../shared/site.js" data-credits="Source A · Source B"></script>
// Built with DOM methods and textContent only (nothing is interpolated into innerHTML).
(function () {
  var me = document.currentScript;
  var credits = (me && me.getAttribute('data-credits')) || '';
  var root = me && me.src ? new URL('../', me.src).href : '/';
  var DISMISS_KEY = 'fieldview_smallscreen_dismissed';

  function el(tag, props, kids) {
    var n = document.createElement(tag);
    Object.keys(props || {}).forEach(function (k) { if (k === 'text') n.textContent = props[k]; else n.setAttribute(k, props[k]); });
    (kids || []).forEach(function (c) { n.appendChild(c); });
    return n;
  }

  var css = document.createElement('style');
  css.textContent =
    '.fv-banner{display:flex;align-items:flex-start;gap:10px;padding:10px 14px;background:#1a2230;color:#e8eaf0;border-bottom:1px solid #f5a623;font:13px/1.4 Barlow,sans-serif;position:relative;z-index:1000}' +
    '.fv-banner span{flex:1}' +
    '.fv-banner button{background:none;border:1px solid #404660;color:#e8eaf0;border-radius:4px;padding:2px 9px;font:inherit;cursor:pointer}' +
    '.fv-footer{border-top:1px solid #1e2330;margin-top:24px;padding:14px 20px 18px;text-align:center;color:#8a93b0;font:11px/1.55 Barlow,sans-serif;background:transparent}' +
    '.fv-footer p{max-width:900px;margin:0 auto 4px}' +
    '.fv-footer a{color:#8a93b0;text-decoration:underline}.fv-footer a:hover{color:#00d4ff}';
  document.head.appendChild(css);

  // Small-screen notice (desktop-only by choice). Dismissal is remembered per browser.
  function dismissed() { try { return localStorage.getItem(DISMISS_KEY) === '1'; } catch (e) { return false; } }
  function showBanner() {
    if (dismissed() || window.innerWidth >= 768 || document.getElementById('fvBanner')) return;
    var btn = el('button', { type: 'button', 'aria-label': 'Dismiss', text: 'Dismiss' });
    var b = el('div', { id: 'fvBanner', class: 'fv-banner', role: 'note' }, [
      el('span', { text: 'FieldView is built for desktop; some views may not fit on small screens.' }), btn]);
    btn.addEventListener('click', function () {
      try { localStorage.setItem(DISMISS_KEY, '1'); } catch (e) {}
      b.remove();
    });
    document.body.insertBefore(b, document.body.firstChild);
  }

  function link(href, text, external) {
    var a = el('a', { href: href });
    a.textContent = text;
    if (external) { a.setAttribute('target', '_blank'); a.setAttribute('rel', 'noopener'); }
    return a;
  }

  function addFooter() {
    var f = el('footer', { class: 'fv-footer' });
    f.appendChild(el('p', { text: 'Not affiliated with or endorsed by the NFL, NBA, MLB, NHL, MLS, Premier League, EA Sports, 2K or their teams. Team names and logos are trademarks of their owners.' }));
    if (credits) f.appendChild(el('p', { text: 'Data: ' + credits + '. Data belongs to its sources.' }));
    var links = el('p');
    links.appendChild(link(root, 'Home'));
    links.appendChild(document.createTextNode(' · '));
    links.appendChild(link(root + 'privacy.html', 'Privacy'));
    links.appendChild(document.createTextNode(' · '));
    links.appendChild(link('https://github.com/jwalluww/fieldview', 'GitHub', true));
    f.appendChild(links);
    document.body.appendChild(f);
  }

  function init() { showBanner(); addFooter(); }
  if (document.body) init(); else document.addEventListener('DOMContentLoaded', init);
})();
