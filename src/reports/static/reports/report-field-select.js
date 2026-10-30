// Choose a field of the report template chosen next to it in a report comparison block: whenever the template
// changes, load its fields into the dropdown. The chosen field's ID is kept in a hidden input.
(function () {
    'use strict';

    const { Controller } = window.StimulusModule;

    class ReportFieldSelectController extends Controller {
        static targets = ['input', 'select'];
        static values = { url: String, emptyLabel: String };

        connect() {
            // The template chooser is the sibling block of the same struct block
            const templateName = this.inputTarget.name.replace(/report_field$/, 'report_type');
            this.templateInput = document.querySelector(`input[name="${CSS.escape(templateName)}"]`);
            this.onTemplateChange = () => this.load();
            // The chooser announces a change through jQuery, which plain event listeners don't hear
            if (this.templateInput) window.jQuery(this.templateInput).on('change', this.onTemplateChange);
            this.load();
        }

        disconnect() {
            if (this.templateInput) window.jQuery(this.templateInput).off('change', this.onTemplateChange);
        }

        async load() {
            const templateId = this.templateInput ? this.templateInput.value : '';
            if (!templateId) {
                this.setOptions(null);
                return;
            }
            const url = `${this.urlValue}?report_type=${encodeURIComponent(templateId)}`;
            const response = await fetch(url, { headers: { Accept: 'application/json' } });
            this.setOptions(response.ok ? (await response.json()).fields : []);
        }

        // Without a template there is nothing to choose from, so the dropdown is disabled. A chosen field that the
        // template doesn't offer is cleared, which leaves the required field empty until another one is chosen.
        setOptions(fields) {
            const options = [new Option(this.emptyLabelValue, '')];
            (fields || []).forEach((field) => options.push(new Option(field.label, field.id)));
            this.selectTarget.replaceChildren(...options);
            this.selectTarget.disabled = fields === null;
            if (!(fields || []).some((field) => field.id === this.inputTarget.value)) {
                this.inputTarget.value = '';
            }
            this.selectTarget.value = this.inputTarget.value;
        }

        choose() {
            this.inputTarget.value = this.selectTarget.value;
        }
    }

    window.wagtail.app.register('report-field-select', ReportFieldSelectController);
})();
