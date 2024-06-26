from __future__ import annotations

from typing import TYPE_CHECKING

from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.views.generic import TemplateView
from wagtail.admin import messages
from wagtail.admin.views.generic.base import (
    BaseObjectMixin, WagtailAdminTemplateMixin
)
from wagtail.admin.views.generic.permissions import PermissionCheckedMixin

from feedback.models import UserFeedback

if TYPE_CHECKING:
    from feedback.wagtail_admin import UserFeedbackPermissionPolicy


class SetUserFeedbackProcessedView(
    BaseObjectMixin,
    PermissionCheckedMixin,
    WagtailAdminTemplateMixin,
    TemplateView
):
    model = UserFeedback
    permission_policy: UserFeedbackPermissionPolicy
    permission_required = 'set_is_processed'
    set_processed = True
    template_name = 'aplans/confirmation.html'
    index_url_name = None

    def user_has_permission(self, permission):
        return self.permission_policy.user_has_permission_for_instance(self.request.user, permission, self.object)

    def get_page_title(self):
        if self.set_processed:
            return _("Mark user feedback as processed")
        else:
            return _("Mark user feedback as unprocessed")

    def get_meta_title(self):
        if self.set_processed:
            msg = _("Confirm marking %(user_feedback)s as processed")
        else:
            msg = _("Confirm marking %(user_feedback)s as unprocessed")
        return msg % {'user_feedback': self.object}

    def confirmation_message(self):
        if self.set_processed:
            msg = _("Do you really want to mark the user feedback '%(user_feedback)s' as processed?")
        else:
            msg = _("Do you really want to mark the user feedback '%(user_feedback)s' as unprocessed?")
        return msg % {'user_feedback': self.object}

    def mark_processed(self):
        if self.object.is_processed:
            raise ValueError(_("The user feedback is already processed"))
        self.object.is_processed = True
        self.object.save()

    def mark_unprocessed(self):
        if not self.object.is_processed:
            raise ValueError(_("The user feedback is already unprocessed"))
        self.object.is_processed = False
        self.object.save()

    def post(self, request, *args, **kwargs):
        try:
            if self.set_processed:
                self.mark_processed()
            else:
                self.mark_unprocessed()
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(self.index_url)
        if self.set_processed:
            msg = _("User feedback '%(user_feedback)s' has been marked as processed.")
        else:
            msg = _("User feedback '%(user_feedback)s' has been marked as unprocessed.")
        messages.success(request, msg % {'user_feedback': self.object})
        return redirect(self.index_url)

    @cached_property
    def index_url(self):
        return reverse(self.index_url_name)
