import importlib

from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig
from django.db.models.fields import BLANK_CHOICE_DASH
from django.utils.translation import get_language_info
from wagtail.admin.localization import get_available_admin_languages


_wagtail_collection_save_instance = None


def collection_save_instance(self):
    instance = self.form.save(commit=False)
    plan = self.request.user.get_active_admin_plan()
    plan.root_collection.add_child(instance=instance)
    return instance


def collection_index_get_queryset(self):
    plan = self.request.user.get_active_admin_plan()
    if plan.root_collection is None:
        return self.model.objects.none()
    else:
        return plan.root_collection.get_descendants(inclusive=False)


def _get_language_choices():
    language_choices = [
        (lang_code, get_language_info(lang_code.lower())['name_local'])
        for lang_code, lang_name in get_available_admin_languages()
    ]
    return sorted(BLANK_CHOICE_DASH + language_choices,
                  key=lambda l: l[1].lower())


class AdminSiteConfig(AdminConfig):
    default_site = 'admin_site.admin.AplansAdminSite'

    def ready(self):
        super().ready()
        # monkeypatch collection create to make new collections as children
        # of root collection of the currently selected plan
        global _wagtail_collection_save_instance
        global _wagtail_collection_index_get_queryset

        if _wagtail_collection_save_instance is None:
            from wagtail.admin.views.collections import Create, Index
            _wagtail_collection_save_instance = Create.save_instance
            Create.save_instance = collection_save_instance
            Index.get_queryset = collection_index_get_queryset

        global _wagtail_preferred_language_choices_func

        # Monkey-patch Wagtail's _get_language_choices to transform language codes to lower case. See the comment above
        # LANGUAGES in settings.py for details about this.
        from wagtail.admin.forms import account
        account.LocalePreferencesForm.base_fields['preferred_language']._choices.choices_func = _get_language_choices


class AdminSiteStatic(AppConfig):
    name = 'admin_site'


if importlib.util.find_spec('kausal_watch_extensions') is not None:
    from kausal_watch_extensions import perform_early_init
    perform_early_init()
