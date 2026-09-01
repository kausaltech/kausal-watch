from __future__ import annotations

from typing import TYPE_CHECKING, override

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy

from kausal_common.i18n.forms import LanguageAwareAdminModelForm
from kausal_common.i18n.helpers import convert_language_code

if TYPE_CHECKING:
    from django.db.models import Model

    from actions.models.plan import Plan


class LoginForm(AuthenticationForm):
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'placeholder': gettext_lazy('Enter password'),
            }
        )
    )

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        email_attrs = self.fields['username'].widget.attrs
        email_attrs['placeholder'] = gettext_lazy('Enter your email address')
        email_attrs['autofocus'] = True

    @property
    def extra_fields(self):
        for field_name, field in self.fields.items():
            if field_name not in ['username', 'password']:
                yield field_name, field

    def clean_username(self):
        return self.cleaned_data['username'].lower()


class WatchAdminModelForm[ModelT: Model](LanguageAwareAdminModelForm[ModelT]):
    plan: Plan | None = None

    @override
    def get_primary_realm_language(self) -> str:
        if self.plan is None:
            raise ValueError('Cannot get plan languages without plan.')
        return convert_language_code(self.plan.primary_language, 'django')

    @override
    def get_all_realm_languages(self) -> set[str]:
        if self.plan is None:
            raise ValueError('Cannot get plan languages without plan.')
        result = set(self.plan.other_languages).union({self.plan.primary_language})
        return {convert_language_code(lang, 'django') for lang in result}

    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan', None)
        self.realm_initialized = self.plan is not None
        super().__init__(*args, **kwargs)
