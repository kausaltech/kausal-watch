from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Model
from django.utils.translation import gettext_lazy
from modeltrans.conf import get_available_languages
from modeltrans.translator import get_i18n_field
from modeltrans.utils import build_localized_fieldname
from wagtail.admin.forms import WagtailAdminModelForm

from actions.models.plan import Plan


class LoginForm(AuthenticationForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': gettext_lazy("Enter password"),
        }))

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)
        email_attrs = self.fields['username'].widget.attrs
        email_attrs['placeholder'] = gettext_lazy("Enter your email address")
        email_attrs['autofocus'] = True

    @property
    def extra_fields(self):
        for field_name, field in self.fields.items():
            if field_name not in ['username', 'password']:
                yield field_name, field

    def clean_username(self):
        return self.cleaned_data['username'].lower()


class WatchAdminModelForm(WagtailAdminModelForm):
    plan: Plan | None = None

    def prune_i18n_fields(self):
        model: type[Model] = self._meta.model
        i18n_field = get_i18n_field(model)
        if not i18n_field:
            return
        other_langs = self.plan.other_languages if self.plan is not None else []
        for base_field_name in i18n_field.fields:
            langs = list(get_available_languages(include_default=True))
            for lang in langs:
                fn = build_localized_fieldname(base_field_name, lang)
                if fn in self.fields and lang not in other_langs:
                    del self.fields[fn]

    def save(self, commit=True):
        obj = super().save(commit)
        return obj

    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop("plan", None)
        super().__init__(*args, **kwargs)
        self.prune_i18n_fields()
