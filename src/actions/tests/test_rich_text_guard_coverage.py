from __future__ import annotations

from django.apps import apps
from wagtail.fields import RichTextField

from kausal_common.models.rich_text import RichTextEditorCompatibleMixin

# First-party apps whose RichTextField models must carry the editor-compatibility guard.
FIRST_PARTY_APP_LABELS = {'actions', 'indicators', 'notifications', 'orgs'}


def test_all_first_party_rich_text_models_have_guard() -> None:
    offenders: list[str] = []
    for model in apps.get_models():
        if model._meta.proxy or model._meta.app_label not in FIRST_PARTY_APP_LABELS:
            continue
        has_rich_text = any(isinstance(f, RichTextField) for f in model._meta.concrete_fields)
        if has_rich_text and not issubclass(model, RichTextEditorCompatibleMixin):
            offenders.append(model._meta.label)
    assert not offenders, (
        f'These models have a RichTextField but not the editor-compatibility guard '
        f'(add RichTextEditorCompatibleMixin): {offenders}'
    )
