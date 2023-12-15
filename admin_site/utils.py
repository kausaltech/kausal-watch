from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _
from django.utils.safestring import mark_safe


def render_html_label_for_visibility(text_content: str | Promise, public: bool):
    class_specifier = 'primary' if public else 'secondary'
    label = _("Public field") if public else _("Non-public field")
    return mark_safe(
        f'{text_content}'
        f'<span class="w-status w-status--{class_specifier} field-visibility-label">'
        f'{label}</span>'
    )


class FieldLabelRenderer:
    """This class provides a function which adds an additional label to field labels, specifying the visibility restrictions for the field
    in question to help users see what information will be shown on the public Watch site and which is for internal users only. The feature
    is switched on with a flag in PlanFeatures; if it's not enabled this doesn't modify the passed field label.

    """
    def __init__(self, plan):
        self.plan_features = plan.features

    def __call__(self, text_content: str |Promise, public: bool = True):
        if self.plan_features.display_field_visibility_restrictions:
            return render_html_label_for_visibility(text_content, public)
        return text_content
