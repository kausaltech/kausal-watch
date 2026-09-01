(function () {
  const ACTIONS_STATUS_CLASS = 'actions-status';
  const WAGTAIL_IS_LOADING_ATTRIBUTE = 'data-w-progress-loading-value';
  const WAGTAIL_LOADING_TEXT_ATTRIBUTE = 'data-w-progress-active-value';

  function waitForElement(selector, all = true, parent = document.body) {
    return new Promise((resolve) => {
      const element = document.querySelector(selector);

      if (element) {
        return resolve(all ? document.querySelectorAll(selector) : element);
      }

      const observer = new MutationObserver((mutations) => {
        const element = document.querySelector(selector);

        if (element) {
          observer.disconnect();
          resolve(all ? document.querySelectorAll(selector) : element);
        }
      });

      observer.observe(parent, {
        childList: true,
        subtree: true,
      });
    });
  }

  function waitForElements(selector) {
    return waitForElement(selector, true);
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
        hiddenInput.getAttribute('aria-describedby'),
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

  /**
   * Reorders the search input and button so that the input is before the button.
   * This is the natural order for screen readers, since the button is used to submit the search.
   */
  async function fixSearchInputAccessibility() {
    const searchForm = await waitForElement(
      '#wagtail-sidebar form[role="search"]',
      false,
      document.getElementById('wagtail-sidebar'),
    );

    if (!searchForm) {
      return;
    }

    const searchButton = searchForm.querySelector('button');
    const searchInput = searchForm.querySelector('input#menu-search-q');
    const wrapper = searchInput.parentNode;

    if (searchInput) {
      searchInput.setAttribute('autocomplete', 'on');
      // TODO: Localize this
      searchInput.setAttribute(
        'aria-description',
        gettext('Please enter a search term'),
      );
    }

    if (!searchButton || !searchInput || !wrapper) {
      return;
    }

    wrapper.insertBefore(searchInput, searchButton);
  }

  function createPublishActionsStatus() {
    const actionsBar = document.querySelector('nav.actions');

    if (actionsBar == null) {
      return;
    }

    const actionsStatus = document.createElement('div');

    actionsStatus.classList.add(ACTIONS_STATUS_CLASS, 'screen-reader-only');
    actionsStatus.setAttribute('aria-live', 'assertive');
    actionsStatus.setAttribute('aria-atomic', 'true');
    actionsStatus.innerText = '';

    actionsBar.appendChild(actionsStatus);
  }

  function createListenersForProgressButtons() {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (
          mutation.type === 'attributes' &&
          mutation.attributeName === WAGTAIL_IS_LOADING_ATTRIBUTE
        ) {
          const status = document.querySelector(`.${ACTIONS_STATUS_CLASS}`);
          const button = mutation.target;

          const isLoading =
            button.getAttribute(WAGTAIL_IS_LOADING_ATTRIBUTE) === 'true';

          if (isLoading) {
            const label = button.getAttribute(WAGTAIL_LOADING_TEXT_ATTRIBUTE);
            button.setAttribute('aria-busy', 'true');
            status.textContent = label || '';
          }
        }
      });
    });

    // Observe all buttons with w-progress controller, for example the save and publish buttons
    const progressButtons = document.querySelectorAll(
      "nav.actions [data-controller*='w-progress']",
    );

    progressButtons.forEach((button) => {
      observer.observe(button, {
        attributes: true,
        attributeFilter: [WAGTAIL_IS_LOADING_ATTRIBUTE],
      });
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
    createPublishActionsStatus();
    createListenersForProgressButtons();
    fixSearchInputAccessibility();
  }

  const accessibilityScript = document.currentScript;
  const accessibilityLevel =
    accessibilityScript.dataset.activePlanAccessibilityLevel;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', (e) =>
      injectAccessibilityFixes(accessibilityLevel),
    );

    return;
  }
  injectAccessibilityFixes(activePlan);
})();
