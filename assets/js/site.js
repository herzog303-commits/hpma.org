/* Hartstene Pointe - nav toggle + gallery lightbox */
(function () {
  // mobile nav
  var toggle = document.querySelector('.nav-toggle');
  var menu = document.querySelector('.nav-menu');
  if (toggle && menu) {
    toggle.addEventListener('click', function () {
      var open = menu.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  // gallery lightbox
  var links = Array.prototype.slice.call(document.querySelectorAll('.gallery a'));
  if (!links.length) return;
  var lb = document.createElement('div');
  lb.className = 'lb';
  lb.innerHTML =
    '<span class="close" aria-label="Close">&times;</span>' +
    '<span class="nav-btn prev" aria-label="Previous">&#8249;</span>' +
    '<img alt="">' +
    '<span class="nav-btn next" aria-label="Next">&#8250;</span>';
  document.body.appendChild(lb);
  var img = lb.querySelector('img');
  var idx = 0;

  function show(i) {
    idx = (i + links.length) % links.length;
    var a = links[idx];
    img.src = a.getAttribute('href');
    img.alt = a.getAttribute('data-caption') || '';
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
