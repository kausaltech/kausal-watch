'use strict';
// Click-to-copy for plan identifiers shown in the Plans admin listing.
(function () {
  function flash(button) {
    button.classList.add('is-copied');
    window.setTimeout(function () {
      button.classList.remove('is-copied');
    }, 1500);
  }

  function copy(text, button) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () {
          flash(button);
        },
        function () {
          /* clipboard denied; silently ignore */
        },
      );
      return;
    }
    // Fallback for browsers/contexts without the async clipboard API.
    var area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'absolute';
    area.style.left = '-9999px';
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand('copy');
      flash(button);
    } catch (err) {
      /* ignore */
    }
    document.body.removeChild(area);
  }

  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-copy-identifier]');
    if (!button) {
      return;
    }
    event.preventDefault();
    copy(button.getAttribute('data-copy-identifier'), button);
  });
})();
