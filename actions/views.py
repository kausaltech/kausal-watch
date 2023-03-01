from django.contrib import messages
from django.contrib.admin.utils import unquote
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from wagtail.contrib.modeladmin.views import WMABaseView

from .forms import CreatePlanWithDefaultsForm
from .models.action import Action
from .models.plan import Plan
from .models.report import ActionSnapshot, Report


def create_plan_with_defaults(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden()
    if request.method == 'POST':
        form = CreatePlanWithDefaultsForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            plan = Plan.create_with_defaults(
                data['plan_identifier'],
                data['plan_name'],
                data['plan_primary_language'],
                data['plan_organization'],
                data['plan_other_languages'],
                data['plan_short_name'],
                base_path=data['base_path'],
                domain=data['domain'],
                client_identifier=data['admin_client_id'],
                client_name=data['client'],
                azure_ad_tenant_id=data['azure_ad_tenant_id']
            )
            return HttpResponseRedirect(
                reverse('change-admin-plan', kwargs=dict(plan_id=plan.id)) + (
                    '?' + 'admin=wagtail')
            )
        else:
            for key, errors in form.errors.as_data().items():
                for error in errors:
                    messages.add_message(request, messages.ERROR, error.message)
            return render(request, 'create_plan/plan_form.html', {'form': form})
    else:
        form = CreatePlanWithDefaultsForm()

    return render(request, 'create_plan/plan_form.html', {'form': form})


class SnapshotActionView(WMABaseView):
    page_title = _("Snapshot action")
    action_pk = None
    report_pk = None
    template_name = 'aplans/confirmation.html'

    def __init__(self, model_admin, action_pk, report_pk):
        self.action_pk = unquote(action_pk)
        self.report_pk = unquote(report_pk)
        self.action = get_object_or_404(Action, pk=self.action_pk)
        self.report = get_object_or_404(Report, pk=self.report_pk)
        super().__init__(model_admin)

    def check_action_permitted(self, user):
        plan = user.get_active_admin_plan()
        return user.is_general_admin_for_plan(plan)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not self.check_action_permitted(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_meta_title(self):
        msg = _("Confirm creating snapshot of %(action)s for report %(report)s")
        return msg % {'action': self.action, 'report': self.report}

    def confirmation_message(self):
        msg = _("Do you really want to create a snapshot of the action '%(action)s' for the report '%(report)s'?")
        return msg % {'action': self.action, 'report': self.report}

    def snapshot(self):
        ActionSnapshot.objects.create(
            report=self.report,
            action=self.action,
        )

    def post(self, request, *args, **kwargs):
        try:
            self.snapshot()
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(self.index_url)
        msg = _("Snapshot of action '%(action)s' has been created for report '%(report)s'.")
        messages.success(request, msg % {'action': self.action, 'report': self.report})
        return redirect(self.index_url)
