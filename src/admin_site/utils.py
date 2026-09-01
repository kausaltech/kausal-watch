from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from generic_chooser.views import ChooserListingTabMixin

if TYPE_CHECKING:
    from django.http.request import HttpRequest
    from django_stubs_ext import StrOrPromise

    from aplans.types import WatchAdminRequest


def render_html_label_for_visibility(text_content: StrOrPromise, public: bool):
    class_specifier = 'primary' if public else 'secondary'
    label = _('Public field') if public else _('Non-public field')
    return format_html(
        '{}<span class="w-status w-status--{} field-visibility-label">{}</span>',
        text_content,
        class_specifier,
        label,
    )


class FieldLabelRenderer:
    """
    Add a visibility label to field labels.

    This helps users distinguish information shown on the public Watch site
    from information available only to internal users. The feature is enabled
    by a flag in PlanFeatures; otherwise the passed field label is unchanged.
    """

    def __init__(self, plan):
        self.plan_features = plan.features

    def __call__(self, text_content: StrOrPromise, public: bool = True):
        if self.plan_features.display_field_visibility_restrictions:
            return render_html_label_for_visibility(text_content, public)
        return text_content


class ChooserListingTabMixinWithEmptyResultsMessage(ChooserListingTabMixin):
    """Override chooser result template to display a message when there are no results."""

    def get_results_template(self):
        # We check whether the object list is empty here rather than in the template because the template only gets a
        # generator, which does not allow us to check for emptiness without exhausting the generator
        if not self.object_list:
            return 'admin_site/chooser_results_empty.html'
        return super().get_results_template()


def admin_req(request: HttpRequest) -> WatchAdminRequest:
    """Cast the HTTP request into an instance of (authenticated) WatchAdminRequest."""
    assert request.user is not None
    assert request.user.is_authenticated
    return cast('WatchAdminRequest', request)
