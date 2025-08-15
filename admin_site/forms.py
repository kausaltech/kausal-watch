from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy
from modeltrans.conf import get_available_languages
from modeltrans.translator import get_i18n_field
from modeltrans.utils import build_localized_fieldname
from wagtail.admin.forms import WagtailAdminModelForm

from kausal_common.i18n.helpers import convert_language_code, get_language_from_default_language_field

if TYPE_CHECKING:
    from django.db.models import Model
    from modeltrans.fields import TranslationField

    from actions.models.plan import Plan


class LoginForm(AuthenticationForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': gettext_lazy("Enter password"),
        }))

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
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


class WatchAdminModelForm[ModelT: Model](WagtailAdminModelForm[ModelT]):
    plan: Plan | None = None

    def get_languages_to_show(self, i18n_field: TranslationField, plan: Plan) -> set[str]:
        """
        Return a list of languages we want to display translation fields for.

        This includes other languages of the plan, but also the
        primary language of the plan, if it's different from the
        primary language of the current model being edited.

        It does not include the original language field without
        the language suffix, since that field is added to the
        form separately.

        Please note: it is not enough nor necessary to hide the
        language variant panels with is_shown since we have to
        remove the form fields here anyway in order for the
        form to be validated correctly.
        """

        if i18n_field.default_language_field:
            original_field_language = get_language_from_default_language_field(self.instance, i18n_field)
        else:
            original_field_language = plan.primary_language

        original_field_language = convert_language_code(original_field_language, 'django')

        languages_to_show: set[str] = set(plan.other_languages).union({ plan.primary_language })
        languages_to_show = {convert_language_code(lang, 'django') for lang in languages_to_show}

        # In the end, we make sure the modeltrans original field -- ie. the field
        # without the language suffix which is saved directly to the original db
        # field and not in the i18n field -- is never shown twice (once here and once as the
        # PrimaryLanguagePanel which was added as a separate panel.
        languages_to_show.remove(original_field_language)
        return languages_to_show

    def prune_i18n_fields(self, plan: Plan):
        i18n_field: TranslationField | None = get_i18n_field(self._meta.model)
        if not i18n_field:
            return
        languages_to_show = self.get_languages_to_show(i18n_field, plan)
        if not languages_to_show:
            return
        for base_field_name in i18n_field.fields:
            langs = list(get_available_languages(include_default=True))
            for lang in langs:
                fn = build_localized_fieldname(base_field_name, lang)
                if lang not in languages_to_show and fn in self.fields:
                    del self.fields[fn]

    def save(self, commit=True):
        obj = super().save(commit)
        return obj

    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop("plan", None)
        super().__init__(*args, **kwargs)
        if self.plan:
            self.prune_i18n_fields(self.plan)
