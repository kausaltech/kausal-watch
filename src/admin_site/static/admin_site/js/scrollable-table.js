'use strict';
// Runtime support for the scrollable pinned-column table idiom (see scrollable-table.css):
//   1. Pin offsets: set each pinned column's sticky `left` to the measured cumulative width of
//      the pinned columns before it, so offsets stay correct even when a pinned column flexes.
//   2. Fill height: size `.kw-scroll-table--fill` containers to the viewport so the listing
//      scrolls inside its own region (horizontal scrollbar on screen, header sticky) rather than
//      making the whole window scroll.
(function () {
  var MIN_HEIGHT = 200;
  var BOTTOM_GAP = 8;

  function setPinOffsets(container) {
    // Measure the pinned columns' widths from a body row (a sticky header cell can misreport its
    // width), build cumulative left offsets, then apply them to the pinned cells of every row
    // (header included — they share the same column order). This keeps the sticky offsets exact
    // even when the table stretches a column, so pinned columns never slide under each other.
    var measureRow = container.querySelector('tbody tr') || container.querySelector('thead tr');
    if (!measureRow) {
      return;
    }
    var measurePins = measureRow.querySelectorAll('.kw-col--pin');
    var offsets = [];
    var acc = 0;
    for (var i = 0; i < measurePins.length; i++) {
      offsets.push(acc);
      acc += measurePins[i].getBoundingClientRect().width;
    }
    var rows = container.querySelectorAll('tr');
    for (var r = 0; r < rows.length; r++) {
      var pins = rows[r].querySelectorAll('.kw-col--pin');
      for (var k = 0; k < pins.length && k < offsets.length; k++) {
        pins[k].style.left = offsets[k] + 'px';
      }
    }
  }

  function sizeFill(el) {
    var rect = el.getBoundingClientRect();
    // Fill from the container's top down to the bottom of the viewport. The admin content area
    // is already pinned to the viewport height, so this does not make the window scroll; it just
    // stops the table short of the very edge.
    var avail = window.innerHeight - rect.top - BOTTOM_GAP;
    el.style.maxHeight = Math.max(avail, MIN_HEIGHT) + 'px';
  }

  function sizeAll() {
    var tables = document.querySelectorAll('.kw-scroll-table');
    for (var i = 0; i < tables.length; i++) {
      var el = tables[i];
      setPinOffsets(el);
      if (el.classList.contains('kw-scroll-table--fill')) {
        sizeFill(el);
      }
    }
  }

  var scheduled = false;
  function schedule() {
    if (scheduled) {
      return;
    }
    scheduled = true;
    window.requestAnimationFrame(function () {
      scheduled = false;
      sizeAll();
    });
  }

  function init() {
    schedule();
    // Re-run after Wagtail swaps the listing results in (filter/search); the swap replaces the
    // #listing-results subtree, including the .kw-scroll-table container.
    var target = document.getElementById('listing-results');
    if (target && 'MutationObserver' in window) {
      new MutationObserver(schedule).observe(target, { childList: true, subtree: true });
    }
  }

  window.addEventListener('resize', schedule);
  window.addEventListener('load', schedule);

  // Run now if the DOM is already parsed (Wagtail injects Media scripts late, so DOMContentLoaded
  // may have already fired by the time this runs); otherwise wait for it.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
