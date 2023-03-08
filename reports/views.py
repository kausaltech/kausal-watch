import reversion
from django.contrib import messages
from django.contrib.admin.utils import unquote
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from reversion.models import Version
from wagtail.contrib.modeladmin.views import WMABaseView

from .models import ActionSnapshot, Report
from actions.models import Action



class MarkActionAsCompleteView(WMABaseView):
    action_pk = None
    report_pk = None
    complete = True
    template_name = 'aplans/confirmation.html'

    def __init__(self, model_admin, action_pk, report_pk, complete=True):
        self.action_pk = unquote(action_pk)
        self.report_pk = unquote(report_pk)
        self.complete = complete
        self.action = get_object_or_404(Action, pk=self.action_pk)
        self.report = get_object_or_404(Report, pk=self.report_pk)
        super().__init__(model_admin)

    def get_page_title(self):
        if self.complete:
            return _("Mark action as complete")
        else:
            return _("Undo marking action as complete")

    def check_action_permitted(self, user):
        plan = user.get_active_admin_plan()
        return user.is_general_admin_for_plan(plan)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not self.check_action_permitted(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_meta_title(self):
        if self.complete:
            msg = _("Confirm marking action %(action)s as complete for report %(report)s")
        else:
            msg = _("Confirm undoing marking action %(action)s as complete for report %(report)s")
        return msg % {'action': self.action, 'report': self.report}

    def confirmation_message(self):
        if self.complete:
            msg = _("Do you really want to mark the action '%(action)s' as complete for the report '%(report)s'?")
        else:
            msg = _("Do you really want to undo marking the action '%(action)s' as complete for the report '%(report)s'?")
        return msg % {'action': self.action, 'report': self.report}

    def create_snapshot(self):
        snapshots = ActionSnapshot.objects.filter(
            report=self.report,
            action_version__in=Version.objects.get_for_object(self.action),
        )
        if snapshots.exists():
            raise ValueError(_("The action is already marked as complete."))
        with reversion.create_revision():
            reversion.add_to_revision(self.action)
            reversion.set_comment(_("Marked action as complete"))
            reversion.set_user(self.request.user)
        ActionSnapshot.objects.create(
            report=self.report,
            action=self.action,
        )

    def delete_snapshot(self):
        snapshots = ActionSnapshot.objects.filter(
            report=self.report,
            action_version__in=Version.objects.get_for_object(self.action),
        )
        num_snapshots = snapshots.count()
        if num_snapshots != 1:
            raise ValueError(_("Cannot undo marking action as complete as there are %s snapshots") % num_snapshots)
        snapshots.delete()

    def post(self, request, *args, **kwargs):
        try:
            if self.complete:
                self.create_snapshot()
            else:
                self.delete_snapshot()
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(self.index_url)
        if self.complete:
            msg = _("Action '%(action)s' has been marked as complete for report '%(report)s'.")
        else:
            msg = _("Action '%(action)s' is no longer marked as complete for report '%(report)s'.")
        messages.success(request, msg % {'action': self.action, 'report': self.report})
        return redirect(self.index_url)
