'use strict';
// Cap a horizontally overflowing listing to the viewport so its horizontal scrollbar stays on
// screen. Listings using the scrollable-table idiom size themselves (scrollable-table.js).
(function () {
  var MIN_HEIGHT = 200;
  var BOTTOM_GAP = 8;

  function unscrolledTop(el) {
    var top = el.getBoundingClientRect().top;
    for (var a = el.parentElement; a; a = a.parentElement) {
      top += a.scrollTop;
    }
    return top;
  }

  function size() {
    var el = document.getElementById('listing-results');
    if (!el || el.querySelector('.kw-scroll-table')) {
      return;
    }
    if (el.scrollWidth <= el.clientWidth) {
      el.style.maxHeight = '';
      el.classList.remove('is-capped');
      return;
    }
    var avail = window.innerHeight - unscrolledTop(el) - BOTTOM_GAP;
    el.style.maxHeight = Math.max(avail, MIN_HEIGHT) + 'px';
    el.classList.add('is-capped');
  }

  var scheduled = false;
  function schedule() {
    if (scheduled) {
      return;
    }
    scheduled = true;
    window.requestAnimationFrame(function () {
      scheduled = false;
      size();
    });
  }

  var resizeObserver = 'ResizeObserver' in window ? new ResizeObserver(schedule) : null;
  var observedTable = null;
  function observeTable(el) {
    var table = el.querySelector('table');
    if (!resizeObserver || table === observedTable) {
      return;
    }
    if (observedTable) {
      resizeObserver.unobserve(observedTable);
    }
    observedTable = table;
    if (table) {
      resizeObserver.observe(table);
    }
  }

  function init() {
    var target = document.getElementById('listing-results');
    if (!target) {
      return;
    }
    if (resizeObserver) {
      resizeObserver.observe(target);
    }
    observeTable(target);
    schedule();
    if ('MutationObserver' in window) {
      new MutationObserver(function () {
        observeTable(target);
        schedule();
      }).observe(target, { childList: true, subtree: true });
    }
  }

  window.addEventListener('resize', schedule);
  window.addEventListener('load', schedule);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
