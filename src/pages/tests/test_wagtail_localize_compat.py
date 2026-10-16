from __future__ import annotations

from uuid import uuid4

from wagtail.blocks import StreamValue
from wagtail.fields import StreamField
from wagtail.models import Locale

import pytest
from wagtail_localize.models import TranslationSource
from wagtail_localize.operations import TranslationCreator
from wagtail_localize.segments.extract import extract_segments

from pages.models import ActionListPage

pytestmark = pytest.mark.django_db


def set_legacy_null_filter(page: ActionListPage) -> None:
    """Give the page a filter block stored as null, like blocks saved while they were `StaticBlock`s."""
    field = ActionListPage._meta.get_field('primary_filters')
    assert isinstance(field, StreamField)
    stream_block = field.stream_block
    raw_data = [{'type': 'status', 'value': None, 'id': str(uuid4())}]
    page.primary_filters = StreamValue(stream_block, raw_data, is_lazy=True)
    page.save()
    page.refresh_from_db()
    stored_filters = page.primary_filters
    assert stored_filters is not None
    assert list(stored_filters.raw_data) == raw_data


@pytest.fixture
def action_list_page(plan_with_pages) -> ActionListPage:
    page = plan_with_pages.root_page.get_children().type(ActionListPage).get().specific
    set_legacy_null_filter(page)
    return page


def test_extract_segments_of_struct_block_stored_as_null(action_list_page):
    segments = extract_segments(action_list_page)
    assert not any(segment.path.startswith('primary_filters.') for segment in segments)


def test_sync_translation_of_page_with_struct_block_stored_as_null(plan_with_pages, action_list_page):
    other_locale = Locale.objects.get(language_code=plan_with_pages.other_languages[0])
    TranslationCreator(user=None, target_locales=[other_locale]).create_translations(action_list_page)
    source = TranslationSource.objects.get_for_instance(action_list_page)

    # This is what the "Sync translated pages" button does
    source.update_from_db()
    source.translations.get(target_locale=other_locale).save_target(publish=True)

    translated_page = action_list_page.get_translation(other_locale).specific
    assert translated_page.primary_filters is not None
    assert [block.block_type for block in translated_page.primary_filters] == ['status']
