import reversion
from django.contrib import messages
from django.contrib.admin.utils import unquote
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import IntegerField
from django.db.models.functions import Cast
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
        return user.can_modify_action(self.action)

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

    def post(self, request, *args, **kwargs):
        try:
            if self.complete:
                self.action.mark_as_complete_for_report(self.report, self.request.user)
            else:
                self.action.undo_marking_as_complete_for_report(self.report, self.request.user)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(self.index_url)
        if self.complete:
            msg = _("Action '%(action)s' has been marked as complete for report '%(report)s'.")
        else:
            msg = _("Action '%(action)s' is no longer marked as complete for report '%(report)s'.")
        messages.success(request, msg % {'action': self.action, 'report': self.report})
        return redirect(self.index_url)


class MarkReportAsCompleteView(WMABaseView):
    report_pk = None
    complete = True
    template_name = 'reports/mark_report_as_complete_confirmation.html'

    def __init__(self, model_admin, report_pk, complete=True):
        self.report_pk = unquote(report_pk)
        self.complete = complete
        self.report = get_object_or_404(Report, pk=self.report_pk)
        super().__init__(model_admin)

    def get_page_title(self):
        if self.complete:
            return _("Mark report as complete")
        else:
            return _("Undo marking report as complete")

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
            msg = _("Confirm marking report %(report)s as complete")
        else:
            msg = _("Confirm undoing marking report %(report)s as complete")
        return msg % {'report': self.report}

    def get_context_data(self, **kwargs):
        context =  super().get_context_data(**kwargs)
        if self.complete:
            complete_actions = Action.objects.complete_for_report(self.report)
            context['affected_actions'] = self.report.type.plan.actions.exclude(id__in=complete_actions)
        else:
            action_ids = (
                ActionSnapshot.objects.filter(report=self.report, created_explicitly=False)
                .annotate(action_id=Cast('action_version__object_id', output_field=IntegerField()))
                .values_list('action_id')
            )
            context['affected_actions'] = Action.objects.filter(id__in=action_ids)
        return context

    def post(self, request, *args, **kwargs):
        try:
            if self.complete:
                self.report.mark_as_complete(self.request.user)
            else:
                self.report.undo_marking_as_complete(self.request.user)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(self.index_url)
        if self.complete:
            msg = _("Report '%(report)s' has been marked as complete.")
        else:
            msg = _("Report '%(report)s' is no longer marked as complete.")
        messages.success(request, msg % {'report': self.report})
        return redirect(self.index_url)
