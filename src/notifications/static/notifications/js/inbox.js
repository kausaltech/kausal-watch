(function () {
  const POLL_MS = 30000;

  function inboxLink() {
    return document.querySelector('[data-inbox-link]');
  }

  async function refresh() {
    const link = inboxLink();
    if (!link || document.hidden) return;
    try {
      const response = await fetch(link.dataset.inboxCountUrl, { credentials: 'same-origin' });
      if (!response.ok) return;
      const { count, label } = await response.json();
      link.toggleAttribute('data-inbox-unread', count > 0);
      if (count > 0) {
        link.setAttribute('title', label);
      } else {
        link.removeAttribute('title');
      }
    } catch (e) {
      // Try again on the next poll
    }
  }

  setInterval(refresh, POLL_MS);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refresh();
  });
})();
