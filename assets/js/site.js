/* Hartstene Pointe - nav toggle + gallery lightbox */
(function () {
  // mobile nav
  var toggle = document.querySelector('.nav-toggle');
  var menu = document.querySelector('.nav-menu');
  var mq = window.matchMedia('(max-width:900px)');
  function collapseSubs() {
    Array.prototype.forEach.call(document.querySelectorAll('.has-sub.expanded'), function (o) {
      o.classList.remove('expanded');
      var a = o.querySelector(':scope > a');
      if (a) a.setAttribute('aria-expanded', 'false');
    });
  }
  if (toggle && menu) {
    toggle.addEventListener('click', function () {
      var open = menu.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (!open) collapseSubs();
    });
  }

  // mobile: tap a top-level parent to expand its submenu instead of navigating.
  // (Each submenu's first item links to the parent's own page, so nothing is lost.)
  Array.prototype.forEach.call(document.querySelectorAll('.has-sub > a'), function (a) {
    a.setAttribute('aria-haspopup', 'true');
    a.setAttribute('aria-expanded', 'false');
    a.addEventListener('click', function (e) {
      if (!mq.matches) return; // desktop keeps hover behaviour and normal links
      e.preventDefault();
      var li = a.parentNode;
      var willOpen = !li.classList.contains('expanded');
      collapseSubs();
      li.classList.toggle('expanded', willOpen);
      a.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    });
  });
  // reset if the viewport grows back to desktop
  mq.addEventListener('change', function (e) { if (!e.matches) collapseSubs(); });

  // gallery lightbox
  var links = Array.prototype.slice.call(document.querySelectorAll('.gallery a'));
  if (!links.length) return;
  var lb = document.createElement('div');
  lb.className = 'lb';
  lb.innerHTML =
    '<span class="close" aria-label="Close">&times;</span>' +
    '<span class="nav-btn prev" aria-label="Previous">&#8249;</span>' +
    '<figure class="lb-figure"><img alt=""><figcaption class="lb-cap"></figcaption></figure>' +
    '<span class="nav-btn next" aria-label="Next">&#8250;</span>';
  document.body.appendChild(lb);
  var img = lb.querySelector('img');
  var cap = lb.querySelector('.lb-cap');
  var idx = 0;

  function show(i) {
    idx = (i + links.length) % links.length;
    var a = links[idx];
    var text = a.getAttribute('data-caption') || '';
    img.src = a.getAttribute('href');
    img.alt = text;
    cap.textContent = text;
    cap.style.display = text ? 'block' : 'none';
    lb.classList.add('open');
  }
  function close() { lb.classList.remove('open'); img.src = ''; }

  links.forEach(function (a, i) {
    a.addEventListener('click', function (e) { e.preventDefault(); show(i); });
  });
  lb.querySelector('.close').addEventListener('click', close);
  lb.querySelector('.next').addEventListener('click', function (e) { e.stopPropagation(); show(idx + 1); });
  lb.querySelector('.prev').addEventListener('click', function (e) { e.stopPropagation(); show(idx - 1); });
  lb.addEventListener('click', function (e) { if (e.target === lb) close(); });
  document.addEventListener('keydown', function (e) {
    if (!lb.classList.contains('open')) return;
    if (e.key === 'Escape') close();
    else if (e.key === 'ArrowRight') show(idx + 1);
    else if (e.key === 'ArrowLeft') show(idx - 1);
  });
})();

/* site search (Pagefind). The index in /pagefind/ is built by the indexer —
   see "Search" in the README. Assets load lazily on first use. */
(function () {
  var btns = document.querySelectorAll('.search-toggle');
  if (!btns.length) return;
  // Site root derived from this script's own URL, so it works at any page depth.
  var root = document.currentScript && document.currentScript.src
    ? document.currentScript.src.replace(/assets\/js\/site\.js.*$/, '')
    : '/';
  var modal = null;
  var cssAdded = false;
  var state = 'idle'; // idle -> loading -> ready; a failed load returns to idle so reopening retries

  function close() {
    modal.classList.remove('open');
    document.documentElement.style.overflow = '';
  }
  function focusInput() {
    var inp = modal.querySelector('.pagefind-ui__search-input');
    if (inp) inp.focus();
  }
  function showError(show) {
    modal.querySelector('.search-error').style.display = show ? 'block' : 'none';
  }
  function build() {
    modal = document.createElement('div');
    modal.className = 'search-modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Search this site');
    modal.innerHTML =
      '<div class="search-panel">' +
      '<div class="search-head"><h2>Search Hartstene Pointe</h2>' +
      '<button class="search-close" aria-label="Close search">&times;</button></div>' +
      '<div class="search-body"><div id="pf-search"></div>' +
      '<p class="search-error" style="display:none">Search isn&rsquo;t available right now. ' +
      'Please try again later, or browse using the menu above.</p></div></div>';
    document.body.appendChild(modal);
    modal.querySelector('.search-close').addEventListener('click', close);
    modal.addEventListener('click', function (e) { if (e.target === modal) close(); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && modal.classList.contains('open')) close();
    });
  }
  function load() {
    state = 'loading';
    if (!cssAdded) {
      cssAdded = true;
      var css = document.createElement('link');
      css.rel = 'stylesheet';
      css.href = root + 'pagefind/pagefind-ui.css';
      document.head.appendChild(css);
    }
    function fail() {
      state = 'idle'; // keep the mount intact; the next open retries the load
      showError(true);
    }
    var js = document.createElement('script');
    js.src = root + 'pagefind/pagefind-ui.js';
    js.onload = function () {
      try {
        new PagefindUI({ element: '#pf-search', showImages: false, showSubResults: true, autofocus: true });
        state = 'ready';
      } catch (e) {
        fail();
      }
    };
    js.onerror = fail;
    document.head.appendChild(js);
  }
  function open() {
    if (!modal) build();
    showError(false);
    modal.classList.add('open');
    document.documentElement.style.overflow = 'hidden';
    if (state === 'idle') load();
    else if (state === 'ready') focusInput();
  }
  Array.prototype.forEach.call(btns, function (b) { b.addEventListener('click', open); });
})();
