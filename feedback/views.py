from django.contrib.admin.utils import unquote
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from wagtail.admin import messages
from wagtail.contrib.modeladmin.views import WMABaseView

from feedback.models import UserFeedback


class SetUserFeedbackProcessedView(WMABaseView):
    user_feedback_pk = None
    set_processed = True
    template_name = 'feedback/set_user_feedback_processed.html'

    def __init__(self, model_admin, user_feedback_pk, set_processed=True):
        self.user_feedback_pk = unquote(user_feedback_pk)
        self.user_feedback = get_object_or_404(UserFeedback, pk=self.user_feedback_pk)
        self.set_processed = set_processed
        super().__init__(model_admin)

    def get_page_title(self):
        if self.set_processed:
            return _("Mark user feedback as processed")
        else:
            return _("Mark user feedback as unprocessed")

    def check_action_permitted(self, user):
        return self.user_feedback.user_can_change_is_processed(user)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not self.check_action_permitted(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_meta_title(self):
        if self.set_processed:
            msg = _("Confirm marking %(user_feedback)s as processed")
        else:
            msg = _("Confirm marking %(user_feedback)s as unprocessed")
        return msg % {'user_feedback': self.user_feedback}

    def confirmation_message(self):
        if self.set_processed:
            msg = _("Do you really want to mark the user feedback '%(user_feedback)s' as processed?")
        else:
            msg = _("Do you really want to mark the user feedback '%(user_feedback)s' as unprocessed?")
        return msg % {'user_feedback': self.user_feedback}

    def mark_processed(self):
        if self.user_feedback.is_processed:
            raise ValueError(_("The user feedback is already processed"))
        self.user_feedback.is_processed = True
        self.user_feedback.save()

    def mark_unprocessed(self):
        if not self.user_feedback.is_processed:
            raise ValueError(_("The user feedback is already unprocessed"))
        self.user_feedback.is_processed = False
        self.user_feedback.save()

    def post(self, request, *args, **kwargs):
        try:
            if self.set_processed:
                self.mark_processed()
            else:
                self.mark_unprocessed()
        except ValueError as e:
            messages.error(request, e)
            return redirect(self.index_url)
        if self.set_processed:
            msg = _("User feedback '%(user_feedback)s' has been marked as processed.")
        else:
            msg = _("User feedback '%(user_feedback)s' has been marked as unprocessed.")
        messages.success(request, msg % {'user_feedback': self.user_feedback})
        return redirect(self.index_url)
