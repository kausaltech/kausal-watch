/*
 * Copy-to-clipboard for the Pledges → Participants admin views.
 *
 * Looks for buttons carrying `data-pledge-participants-emails`. On click,
 * writes the value to the clipboard and briefly swaps the label so the
 * operator gets confirmation. No framework dependencies — Wagtail admin
 * pages load this from insert_global_admin_js.
 */
(function () {
  'use strict';

  function onCopyClick(button) {
    var emails = button.getAttribute('data-pledge-participants-emails') || '';
    if (!emails) {
      return;
    }
    var done = function () {
      var original = button.textContent;
      button.textContent = button.getAttribute('data-pledge-participants-copied-label') || 'Copied';
      button.disabled = true;
      setTimeout(function () {
        button.textContent = original;
        button.disabled = false;
      }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(emails).then(done, function () {
        fallbackCopy(emails);
        done();
      });
    } else {
      fallbackCopy(emails);
      done();
    }
  }

  function fallbackCopy(text) {
    var textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'absolute';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand('copy');
    } catch (e) {
      /* swallow */
    }
    document.body.removeChild(textarea);
  }

  function init() {
    document.body.addEventListener('click', function (event) {
      var target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      var button = target.closest('[data-pledge-participants-emails]');
      if (button) {
        event.preventDefault();
        onCopyClick(button);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
