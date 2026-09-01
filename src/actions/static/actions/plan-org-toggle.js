(function () {
    'use strict';

    function setChooserDisabled(disabled) {
        var chooser = document.getElementById('id_organization-chooser');
        if (!chooser) return;

        chooser.querySelectorAll(
            '[data-chooser-action-choose], [data-chooser-action-clear]'
        ).forEach(function (btn) {
            btn.disabled = disabled;
        });

        if (disabled) {
            chooser.style.opacity = '0.5';
            chooser.style.pointerEvents = 'none';
        } else {
            chooser.style.opacity = '';
            chooser.style.pointerEvents = '';
        }
    }

    function update() {
        var orgInput = document.getElementById('id_organization');
        var nameInput = document.getElementById('id_organization_name');
        if (!orgInput || !nameInput) return;

        var hasOrg = orgInput.value && orgInput.value !== '';
        var hasName = nameInput.value.trim() !== '';

        // Org selected → disable name field
        nameInput.disabled = hasOrg;
        if (hasOrg) {
            nameInput.value = '';
        }

        // Name entered → disable chooser
        setChooserDisabled(hasName);
    }

    function init() {
        var orgInput = document.getElementById('id_organization');
        var nameInput = document.getElementById('id_organization_name');
        if (!orgInput || !nameInput) return;

        update();

        // Wagtail chooser widgets update the hidden input's value attribute,
        // so we observe attribute changes on the input element.
        var observer = new MutationObserver(update);
        observer.observe(orgInput, { attributes: true, attributeFilter: ['value'] });

        // Also listen for regular change events on the chooser as a fallback.
        orgInput.addEventListener('change', update);

        // Listen for typing in the name field.
        nameInput.addEventListener('input', update);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
