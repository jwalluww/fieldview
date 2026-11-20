// FieldView shared site chrome: small-screen notice + trademark/credits footer.
// Included on every page with:  <script src="../shared/site.js" data-credits="Source A · Source B"></script>
// Field views add data-mode="popup": no footer (they fit the viewport); the same disclaimer + credits + links
// open from a "Credits & disclaimer" button in the header instead (Esc, x and a backdrop click close it).
// Built with DOM methods and textContent only (nothing is interpolated into innerHTML).
(function () {
  var me = document.currentScript;
  var credits = (me && me.getAttribute('data-credits')) || '';
  var popup = !!(me && me.getAttribute('data-mode') === 'popup');
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
    '.fv-footer a{color:#8a93b0;text-decoration:underline}.fv-footer a:hover{color:#00d4ff}' +
    '.fv-credits-btn{margin-left:12px;background:none;border:0;color:#8a93b0;font:12px Barlow,sans-serif;text-decoration:underline;cursor:pointer;white-space:nowrap;padding:4px 2px}' +
    '.fv-credits-btn:hover{color:#00d4ff}' +
    '.fv-modal-back{position:fixed;inset:0;z-index:2000;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;padding:16px}' +
    '.fv-modal{position:relative;max-width:560px;width:100%;background:#12151d;border:1px solid #2a3042;border-radius:10px;padding:22px 26px 18px;color:#e8eaf0;font:13px/1.55 Barlow,sans-serif}' +
    '.fv-modal h2{margin:0 0 10px;font:700 18px "Barlow Condensed",Barlow,sans-serif;letter-spacing:1px;text-transform:uppercase}' +
    '.fv-modal p{margin:0 0 8px;color:#b4bbd0}' +
    '.fv-modal a{color:#8a93b0;text-decoration:underline}.fv-modal a:hover{color:#00d4ff}' +
    '.fv-modal-x{position:absolute;top:8px;right:10px;background:none;border:0;color:#8a93b0;font-size:22px;line-height:1;cursor:pointer}.fv-modal-x:hover{color:#e8eaf0}';
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

  // One source of truth: the disclaimer, credits and links, appended to a footer or the popup.
  function fillCredits(box, withTables) {
    box.appendChild(el('p', { text: 'Not affiliated with or endorsed by the NFL, NBA, MLB, NHL, MLS, Premier League, EA Sports, 2K or their teams. Team names and logos are trademarks of their owners.' }));
    if (credits) box.appendChild(el('p', { text: 'Data: ' + credits + '. Data belongs to its sources.' }));
    var links = el('p');
    links.appendChild(link(root, 'Home'));
    links.appendChild(document.createTextNode(' · '));
    links.appendChild(link(root + 'privacy.html', 'Privacy'));
    links.appendChild(document.createTextNode(' · '));
    links.appendChild(link('https://github.com/jwalluww/fieldview', 'GitHub', true));
    box.appendChild(links);
    if (withTables) {   // the table pages are hidden from the nav but still load at their URLs
      var t = el('p', { class: 'fv-tables' });
      t.appendChild(document.createTextNode('League tables: '));
      [['NFL', 'nfl/depth-chart.html'], ['NBA', 'nba/player-table.html'], ['MLB', 'mlb/player-table.html'],
       ['NHL', 'nhl/player-table.html'], ['EPL', 'epl/player-table.html'], ['MLS', 'mls/player-table.html']].forEach(function (x, i) {
        if (i) t.appendChild(document.createTextNode(' · '));
        t.appendChild(link(root + x[1], x[0]));
      });
      box.appendChild(t);
    }
  }

  function addFooter() {
    var f = el('footer', { class: 'fv-footer' });
    fillCredits(f);
    document.body.appendChild(f);
  }

  var lastFocus = null;
  function closeModal() {
    var m = document.getElementById('fvCredits');
    if (m) m.remove();
    document.removeEventListener('keydown', onKey, true);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  function onKey(e) {
    if (e.key === 'Escape' && document.getElementById('fvCredits')) { e.stopPropagation(); closeModal(); }
  }
  function openModal() {
    if (document.getElementById('fvCredits')) return;
    lastFocus = document.activeElement;
    var x = el('button', { type: 'button', class: 'fv-modal-x', 'aria-label': 'Close', text: '×' });
    var box = el('div', { class: 'fv-modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Credits and disclaimer' },
      [x, el('h2', { text: 'Credits & disclaimer' })]);
    fillCredits(box, true);
    var back = el('div', { id: 'fvCredits', class: 'fv-modal-back' }, [box]);
    back.addEventListener('click', function (e) { if (e.target === back) closeModal(); });
    x.addEventListener('click', closeModal);
    document.addEventListener('keydown', onKey, true);
    document.body.appendChild(back);
    x.focus();
  }
  function addCreditsButton() {
    var header = document.querySelector('header.header');
    if (!header) { addFooter(); return; }   // no header to host the button: keep the footer
    var b = el('button', { type: 'button', class: 'fv-credits-btn', id: 'fvCreditsBtn', text: 'Credits & disclaimer' });
    b.addEventListener('click', openModal);
    header.appendChild(b);
  }

  function init() { showBanner(); if (popup) addCreditsButton(); else addFooter(); }
  if (document.body) init(); else document.addEventListener('DOMContentLoaded', init);
})();
