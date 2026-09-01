from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.utils.translation import gettext
from wagtail.admin.rich_text import DraftailRichTextArea
from wagtail.admin.rich_text.editors.draftail import DraftailRichTextAreaAdapter


# Workaround until https://github.com/wagtail/wagtail/pull/11075 is merged
def _hack_rich_text_editor_options(options: dict) -> None:
    type_to_trans_map = {
        'LINK': gettext('Link'),
        'DOCUMENT': gettext('Document'),
        'EMBED': gettext('Embed'),
        'IMAGE': gettext('Image'),
        'BOLD': gettext('Bold'),
        'ITALIC': gettext('Italic'),
        'SUPERSCRIPT': gettext('Superscript'),
        'SUBSCRIPT': gettext('Subscript'),
        'header-two': gettext('Heading %(level)d') % {'level': 2},
        'header-three': gettext('Heading %(level)d') % {'level': 3},
        'header-four': gettext('Heading %(level)d') % {'level': 4},
        'ordered-list-item': gettext('Numbered list'),
        'unordered-list-item': gettext('Bulleted list'),
    }
    for option in options.values():
        if not isinstance(option, list):
            continue
        for item in option:
            if not isinstance(item, dict):
                continue
            item_type = item.get('type')
            if not item_type:
                continue
            new_trans = type_to_trans_map.get(item_type)
            if not new_trans:
                continue
            item['description'] = new_trans


class DraftailRichTextAreaWithFixedTranslations(DraftailRichTextArea):
    options: dict[str, Any]

    def get_context(self, name, value, attrs):
        old_options: dict[str, Any] = self.options
        self.options = deepcopy(old_options)
        _hack_rich_text_editor_options(self.options)
        context = super().get_context(name, value, attrs)
        self.options = old_options
        return context


class DraftailRichTextAreaAdapterWithFixedTranslations(DraftailRichTextAreaAdapter):
    def js_args(self, widget):
        dicts = super().js_args(widget)
        for d in dicts:
            _hack_rich_text_editor_options(d)
        return dicts
