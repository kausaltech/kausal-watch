from django.contrib import messages
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .forms import CreatePlanWithDefaultsForm
from .models.plan import Plan


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
                client_name=data['client'],
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
