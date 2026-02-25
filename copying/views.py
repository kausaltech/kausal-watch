from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.text import capfirst
from django.utils.translation import gettext as _, gettext_lazy
from django.views.generic import FormView
from wagtail.admin.views.generic.base import WagtailAdminTemplateMixin

from celery.contrib.django.task import DjangoTask
from loguru import logger

from actions.models.plan import Plan
from copying.main import may_copy_indicators
from copying.tasks import copy_plan

if TYPE_CHECKING:
    from django.http import HttpResponse
    from django_stubs_ext import StrOrPromise

    from users.models import User


class PlanCopyForm(forms.Form):
    def __init__(self, plan_id: int, user: User, *args, **kwargs):
        self.plan_id = plan_id
        self.user = user
        self.plan = Plan.objects.get(id=plan_id)
        super().__init__(*args, **kwargs)
        self.fields['identifier'] = forms.CharField(
            label=_("Identifier"),
            help_text=_(
                "A unique value that identifies the copy internally and appears in URLs of testing or preview "
                "environments"
            ),
            initial=self.plan.default_identifier_for_copying(),
        )
        self.fields['name'] = forms.CharField(
            label=_("Name"),
            help_text=_("Name to use for the copy"),
            initial=self.plan.default_name_for_copying(),
        )
        self.fields['version_name'] = forms.CharField(
            label=_("Version name"),
            help_text=_("Version name to be set for the copied plan in order to distinguish it from other versions"),
            initial=self.plan.default_version_name_for_copying(),
            required=False,
        )
        self.fields['supersede_original_plan'] = forms.BooleanField(
            label=_("Supersede original plan"),
            help_text=_("Set if the copy should supersede the original plan"),
            initial=False,
            required=False,
        )
        self.fields['supersede_original_actions'] = forms.BooleanField(
            label=_("Supersede original actions"),
            help_text=_("Set if copies of actions should supersede their original"),
            initial=False,
            required=False,
        )
        self.fields['copy_indicators'] = forms.BooleanField(
            label=_("Copy indicators"),
            help_text=_(
                "Set if indicators should be copied instead of being shared with the original plan. "
                "Indicators can only be copied if no indicator is shared with another plan or is an instance of a common "
                "indicator."
            ),
            initial=False,
            required=False,
            disabled=not may_copy_indicators(self.plan),
        )

    def clean_identifier(self) -> str:
        identifier = self.cleaned_data['identifier']
        if Plan.objects.filter(identifier=identifier).exists():
            raise ValidationError(_("A plan with this identifier already exists"))
        return identifier

    def clean_name(self) -> str:
        # The name must be unique even though the model field does not require it, otherwise `Plan.save()` will try to
        # create an admin group with a duplicate name, causing an error.
        name = self.cleaned_data['name']
        if Plan.objects.filter(name=name).exists():
            raise ValidationError(_("A plan with this name already exists"))
        return name



class PlanCopyView(WagtailAdminTemplateMixin, FormView):
    plan_id: int | None = None

    form_class = PlanCopyForm
    page_title = gettext_lazy("Copy plan")
    template_name = 'wagtailadmin/generic/form.html'
    plan_list_url_name = 'wagtailsnippets_actions_plan:list'

    header_icon = 'kausal-plan'
    _show_breadcrumbs = True  # using a not yet released Wagtail feature is not our biggest sin

    def get_page_subtitle(self) -> StrOrPromise:
        plan = Plan.objects.get(id=self.plan_id)
        return plan.name

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs['plan_id'] = self.plan_id
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self) -> str:
        return reverse(self.plan_list_url_name)

    def get_breadcrumbs_items(self):
        items = list(super().get_breadcrumbs_items())
        plans_label = capfirst(Plan._meta.verbose_name_plural)
        if plans_label:  # for the type checker; should be true anyway, but I like this more than `assert plans_label`
            items.append(
                {
                    'url': reverse(self.plan_list_url_name),
                    'label': plans_label,
                }
            )
        items.append(
            {
                'url': '',
                'label': self.get_page_title(),
                'sublabel': self.get_page_subtitle(),
            }
        )
        return items

    def form_valid(self, form) -> HttpResponse:
        logger.info(f"Queueing task for copying plan {self.plan_id}")
        assert isinstance(copy_plan, DjangoTask)
        copy_plan.delay_on_commit(
            plan_id=self.plan_id,
            new_plan_identifier=form.cleaned_data['identifier'],
            new_plan_name=form.cleaned_data['name'],
            version_name=form.cleaned_data['version_name'],
            supersede_original_plan=form.cleaned_data['supersede_original_plan'],
            supersede_original_actions=form.cleaned_data['supersede_original_actions'],
            copy_indicators=form.cleaned_data['copy_indicators'],
        )
        messages.success(self.request, _(
            "The copy will be created in the background. This may take a few minutes. The copy will appear in the list "
            "of plans as soon as copying is finished."
        ))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["media"] = context["form"].media
        context["submit_button_label"] = _("Create copy")
        return context
