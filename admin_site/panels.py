from __future__ import annotations

from typing import Any

from django.conf import settings
from modeltrans.utils import build_localized_fieldname
from wagtail.admin.panels import FieldPanel, FieldRowPanel, MultiFieldPanel

from aplans.types import WatchAdminRequest


class TranslatedLanguagePanel(FieldPanel):
    main_field_name: str
    language: str

    def __init__(self, field_name: str, language: str, **kwargs):
        self.main_field_name = field_name
        self.language = language
        field_name = build_localized_fieldname(field_name, language.lower(), default_language='')
        super().__init__(field_name, **kwargs)

    def clone_kwargs(self):
        ret = super().clone_kwargs()
        ret['field_name'] = self.main_field_name
        ret['language'] = self.language
        return ret

    class BoundPanel(FieldPanel.BoundPanel):
        panel: TranslatedLanguagePanel
        request: WatchAdminRequest

        def is_shown(self):
            plan = self.request.get_active_admin_plan()
            ret = super().is_shown()
            if not ret:
                return False
            return self.panel.language in plan.other_languages


class TranslatedFieldMixin:
    def __init__(self, field_name: str, widget: Any = None, **kwargs):
        self.field_name = field_name
        self.widget = widget
        primary_panel = FieldPanel(field_name, widget=widget, **kwargs)
        lang_panels = [TranslatedLanguagePanel(
            field_name=field_name,
            language=lang[0],
            widget=widget,
            **kwargs
        ) for lang in settings.LANGUAGES]
        super().__init__(children=[primary_panel, *lang_panels], **kwargs)  # type: ignore

    def clone_kwargs(self):
        ret = super().clone_kwargs()  # type: ignore
        del ret['children']
        ret['field_name'] = self.field_name
        ret['widget'] = self.widget
        return ret


class TranslatedFieldRowPanel(TranslatedFieldMixin, FieldRowPanel):
    """Panel that automatically adds panels also for translated versions of the
    string according to the languages of the action plan. The panels are added
    side by side.
    """
    pass


class TranslatedFieldPanel(TranslatedFieldMixin, MultiFieldPanel):
    """Panel that automatically adds panels also for translated versions of the
    string according to the languages of the action plan. The panels are added
    on top of each other.
    """
    pass
