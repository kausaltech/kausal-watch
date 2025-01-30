(function() {

  function waitForElements(selector) {
    return new Promise(resolve => {
      if (document.querySelector(selector)) {
        return resolve(document.querySelectorAll(selector));
      }

      const observer = new MutationObserver(mutations => {
        if (document.querySelector(selector)) {
          observer.disconnect();
          resolve(document.querySelectorAll(selector));
        }
      });

      observer.observe(document.body, {
        childList: true,
        subtree: true
      });
    });
  }

  async function fixDraftailDescribedByElements() {
    const elList = await waitForElements('.public-DraftEditor-content');
    elList.forEach((el) => {
      const hiddenInput = el.closest('.w-field__input')?.querySelector('input');
      if (hiddenInput == null) {
        return;
      }
      el.setAttribute(
        'aria-describedby',
        hiddenInput.getAttribute('aria-describedby')
      );
    });

  }

  function addAttributesToNotificationMessages() {
    /*
    Fixes problem with screen reader not being able to detect Wagtail
    status messages.
     */
    const messageContainers = document.querySelectorAll('.messages');
    messageContainers.forEach(function (container) {
      container.setAttribute('role', 'alert');
      container.setAttribute('aria-live', 'assertive');
      container.setAttribute('aria-atomic', 'true');
      if (container.innerText) {
        container.setAttribute('aria-label', container.innerText);
      }
    });
  }

  function addActivePlanAccessibilityFlagToBodyClass(accessibilityLevel) {
    /*
    Some CSS styles must only be used when the plan explicitly requires them.
    Inject the accessibility class of the plan if it's not the default.
     */
    if (accessibilityLevel === 'default') {
      return;
    }
    const rootElement = document.body;
    rootElement.className = `${rootElement.className} watch-active-accessibility-level-${accessibilityLevel}`;
  }

  function injectAccessibilityFixes(accessibilityLevel) {
    addActivePlanAccessibilityFlagToBodyClass(accessibilityLevel);
    addAttributesToNotificationMessages();
    fixDraftailDescribedByElements();
  }

  const accessibilityScript = document.currentScript;
  const accessibilityLevel = accessibilityScript.dataset.activePlanAccessibilityLevel;

  if (document.readyState === 'loading') {
    document.addEventListener(
      'DOMContentLoaded',
      (e) => injectAccessibilityFixes(accessibilityLevel)
    );
    return;
  }
  injectAccessibilityFixes(activePlan);

})();
