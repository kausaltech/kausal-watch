"""Find the pages whose content blocks show an indicator, so that deleting it doesn't break them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import TextField
from django.db.models.functions import Cast
from wagtail.blocks import ListBlock, StreamBlock, StructBlock
from wagtail.fields import StreamField
from wagtail.models import Page, ReferenceIndex, Revision

if TYPE_CHECKING:
    from collections.abc import Iterator

    from wagtail.blocks import Block

    from indicators.models import Indicator


@dataclass
class IndicatorUsage:
    """The pages that show an indicator in one of their content blocks."""

    pages: list[Page] = field(default_factory=list)
    """Pages whose current content has a block showing the indicator."""

    draft_pages: list[Page] = field(default_factory=list)
    """Pages not in `pages` whose unpublished draft has a block showing the indicator."""

    @property
    def blocks_deletion(self) -> bool:
        return bool(self.pages or self.draft_pages)


def _chosen_indicator_ids(block: Block, value: Any) -> Iterator[int]:
    """Yield the IDs of the indicators chosen in an indicator chooser anywhere within the block value."""
    from indicators.blocks import IndicatorChooserBlock

    if value is None:
        return
    if isinstance(block, IndicatorChooserBlock):
        yield value.pk
    elif isinstance(block, StreamBlock):
        for child in value:
            yield from _chosen_indicator_ids(child.block, child.value)
    elif isinstance(block, ListBlock):
        for item in value:
            yield from _chosen_indicator_ids(block.child_block, item)
    elif isinstance(block, StructBlock):
        for name, child_block in block.child_blocks.items():
            yield from _chosen_indicator_ids(child_block, value.get(name))


def page_shows_indicator(page: Page, indicator: Indicator) -> bool:
    """
    Tell whether one of the page's content blocks shows the indicator.

    Rich text links to the indicator don't count: they are rendered without a target once the indicator is gone,
    which does not break the page.
    """
    for page_field in page._meta.get_fields():
        if not isinstance(page_field, StreamField):
            continue
        stream_value = getattr(page, page_field.name)
        if indicator.pk in _chosen_indicator_ids(page_field.stream_block, stream_value):
            return True
    return False


def _candidate_page_ids(indicator: Indicator) -> set[int]:
    # The indicator chooser offers the indicators of the active plan, so the pages of the indicator's plans (in any
    # of their languages) are the ones that can show it. The reference index additionally covers pages of plans the
    # indicator has been removed from since it was chosen, but it only knows about published content.
    page_ids: set[int] = set()
    for plan in indicator.plans.all():
        if plan.site_id is None:
            continue
        for root in plan.root_page.get_translations(inclusive=True):
            page_ids.update(Page.objects.descendant_of(root, inclusive=True).values_list('pk', flat=True))
    referencing_page_ids = (
        ReferenceIndex
        .get_references_to(indicator)
        .filter(base_content_type=ContentType.objects.get_for_model(Page))
        .values_list('object_id', flat=True)
    )
    page_ids.update(int(pk) for pk in referencing_page_ids)
    page_ids.update(_ids_of_pages_with_draft_mentioning(indicator))
    return page_ids


def _ids_of_pages_with_draft_mentioning(indicator: Indicator) -> Iterator[int]:
    # Neither of the above finds a draft that chose the indicator in a plan the indicator has left since. Checking
    # every draft in the database would be too slow, but a draft that chose the indicator must contain its ID as a
    # number, so only drafts that do need a closer look.
    draft_revisions = Page.objects.filter(has_unpublished_changes=True).values('latest_revision_id')
    object_ids = (
        Revision.objects
        .filter(pk__in=draft_revisions)
        .annotate(content_text=Cast('content', TextField()))
        .filter(content_text__regex=rf'(^|[^0-9]){indicator.pk}([^0-9]|$)')
        .values_list('object_id', flat=True)
    )
    return (int(pk) for pk in object_ids)


def get_indicator_usage(indicator: Indicator) -> IndicatorUsage:
    usage = IndicatorUsage()
    pages = Page.objects.get_queryset().filter(pk__in=_candidate_page_ids(indicator)).order_by('path').specific()
    for page in pages:
        _add_page_usage(usage, page, indicator)
    return usage


def _add_page_usage(usage: IndicatorUsage, page: Page, indicator: Indicator) -> None:
    if page_shows_indicator(page, indicator):
        usage.pages.append(page)
        return
    if not page.has_unpublished_changes or page.latest_revision is None:
        return
    if page_shows_indicator(page.latest_revision.as_object(), indicator):
        usage.draft_pages.append(page)
