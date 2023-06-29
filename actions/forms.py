import re

from django import forms
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _

from aplans.utils import get_supported_languages
from orgs.models import Organization
from .models import Plan


class CreatePlanWithDefaultsForm(forms.Form):
    error_css_class = 'error'
    required_css_class = 'required'

    plan_name = forms.CharField(
        label=_('Plan name'), max_length=100,
        help_text=_('The official plan name in full form')
    )
    plan_identifier = forms.CharField(
        label=_('Plan identifier'), max_length=50, min_length=4,
        help_text=_('An unique identifier for the plan used internally to distinguish between plans. '
                    'This becomes part of the test site URL: https://&lt;plan-identifier&gt;.test.kausal.tech. '
                    'Use lowercase letters and dashes.')
    )
    plan_primary_language = forms.ChoiceField(
        label=_('Primary language'), choices=get_supported_languages
    )
    plan_organization = forms.ModelChoiceField(
        label=_('Main organization'),
        queryset=Organization.get_root_nodes()
    )
    plan_short_name = forms.CharField(
        label=_('Short name of plan'), max_length=100, required=False,
        help_text=_('A shorter version of the plan name')
    )
    plan_other_languages = forms.MultipleChoiceField(
        label=_('Other languages'), choices=(get_supported_languages),
        required=False
    )
    domain = forms.CharField(
        label=_('Domain name'),
        max_length=100,
        required=False,
        help_text=_('The fully qualified domain name, eg. climate.cityname.gov. Leave blank if not yet known')
    )
    base_path = forms.CharField(
        label=_('Base path'),
        max_length=50,
        required=False,
        help_text=_('Fill this for a multi-plan site when the plan does not live in the root of the domain')

    )
    client = forms.CharField(
        label=_('Name of client'),
        max_length=200,
        required=False,
        help_text=_('Name of the customer administering the plan')
    )
    admin_client_id = forms.CharField(
        label=_('Client subdomain for admin UI'),
        max_length=100,
        required=False,
        help_text=_('A lowercase short name which becomes part of the admin UI address - '
                    'for example, "sunnydale" in sunnydale.watch.kausal.tech')
    )

    def clean_plan_identifier(self):
        identifier = self.cleaned_data['plan_identifier']
        if Plan.objects.filter(identifier=identifier).count() > 0:
            raise ValidationError(_('Identifier already in use'), code='identifier-taken')
        if not re.fullmatch('([a-z]+-)*[a-z]+', identifier):
            raise ValidationError(
                _('For identifiers, use only lowercase letters from the English alphabet with dashes separating words')
            )
        return identifier

    def clean_plan_name(self):
        name = self.cleaned_data['plan_name']
        if Plan.objects.filter(name=name).count() > 0:
            raise ValidationError(_('Plan name already in use'), code='name-taken')
        return name

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data['plan_primary_language'] in cleaned_data['plan_other_languages']:
            raise ValidationError(_(
                'A plan\'s other language cannot be the same as its primary language'),
                                  code='plan-language-duplicate'
            )
        return cleaned_data
