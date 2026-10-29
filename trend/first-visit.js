/* First visit: a reader who opens the site's front page for the first time is sent to Vol.01.
   Every page loads this file, so a visit to any page counts; only a first-ever visit to the front page redirects.
   On Vol.01 opened this way, a bar offers the latest issue. Per browser (localStorage); fails open. */
(function () {
  var KEY = 'ats_seen', FIRST = 'issues/2026-10-15.html';
  var me = document.currentScript, root = new URL('.', me.src).pathname;
  var path = location.pathname, seen = null;
  try { seen = localStorage.getItem(KEY); localStorage.setItem(KEY, '1'); } catch (e) { seen = '1'; }
  if (!seen && (path === root || path === root + 'index.html')) {
    location.replace(root + FIRST + '?from=first');
    return;
  }
  if (/[?&]from=first\b/.test(location.search)) {
    var ko = (document.documentElement.lang || '').indexOf('ko') === 0;
    var add = function () {
      var w = document.querySelector('.wrap'); if (!w) return;
      var bar = document.createElement('div');
      bar.className = 'firstbar';
      bar.setAttribute('role', 'note');
      bar.innerHTML = '<span>' + (ko ? '처음 오셨네요. 1회차부터 소개해 드려요.' : 'New here? Start with our first issue.') + '</span>' +
        '<a href="' + root + 'index.html">' + (ko ? '최신 호 보기 →' : 'Read the latest issue →') + '</a>';
      w.insertBefore(bar, w.firstChild);
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
  }
})();
