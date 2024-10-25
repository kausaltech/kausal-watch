from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block

from actions.blocks.action_content import (
    ActionAsideContentBlock,
    ActionContactFormBlock,
    # If you're wondering about unknown import symbol errors:
    # The types below are defined by metaprogramming
    ActionContactPersonsBlock,  # type: ignore
    ActionDependenciesBlock,  # type: ignore
    ActionDescriptionBlock,  # type: ignore
    ActionLeadParagraphBlock,  # type: ignore
    ActionLinksBlock,  # type: ignore
    ActionMainContentBlock,
    ActionMergedActionsBlock,  # type: ignore
    ActionOfficialNameBlock,
    ActionRelatedActionsBlock,  # type: ignore
    ActionRelatedIndicatorsBlock,  # type: ignore
    ActionResponsiblePartiesBlock,
    ActionScheduleBlock,  # type: ignore
    ActionTasksBlock,  # type: ignore
)
from actions.blocks.action_dashboard import (
    ActionDashboardColumnBlock,
    EndDateColumnBlock,
    FieldColumnBlock,
    IdentifierColumnBlock,
    ImpactColumnBlock,
    ImplementationPhaseColumnBlock,
    IndicatorsColumnBlock,
    NameColumnBlock,
    OrganizationColumnBlock,
    ResponsiblePartiesColumnBlock,
    StartDateColumnBlock,
    StatusColumnBlock,
    TasksColumnBlock,
    UpdatedAtColumnBlock,
)
from actions.blocks.action_list import ActionHighlightsBlock, ActionListBlock
from actions.blocks.category_list import CategoryListBlock, CategoryTreeMapBlock, CategoryTypeLevelListBlock
from actions.blocks.choosers import (
    ActionAttributeTypeChooserBlock,
    AttributeTypeChooserBlock,
    CategoryAttributeTypeChooserBlock,
    CategoryChooserBlock,
    CategoryTypeChooserBlock,
)
from actions.blocks.filters import (
    ActionImplementationPhaseFilterBlock,
    ActionListFilterBlock,
    ActionScheduleFilterBlock,
    ContinuousActionFilterBlock,
    PrimaryOrganizationFilterBlock,
    ResponsiblePartyFilterBlock,
)
from actions.models.attributes import AttributeType, AttributeTypeQuerySet
from actions.models.category import CategoryType
from actions.models.plan import Plan


def get_default_action_content_blocks(plan: Plan) -> dict[str, Any]:
    action_ats: AttributeTypeQuerySet = AttributeType.objects.for_actions(plan)
    action_cts = plan.category_types.filter(categories__actions__isnull=False, usable_for_actions=True).distinct()

    main_blocks_top = [
        {'type': 'lead_paragraph', 'value': None},
        {'type': 'description', 'value': None},
        {'type': 'official_name', 'value': None},
        {'type': 'links', 'value': None},
        {'type': 'merged_actions', 'value': None},
        *[{'type': 'attribute', 'value': dict(attribute_type=atype.id)} for atype in action_ats],
        {'type': 'tasks', 'value': None},
    ]
    aside_blocks = [
        {'type': 'schedule', 'value': None},
        {'type': 'responsible_parties', 'value': None},
        *[{'type': 'categories', 'value': dict(category_type=ct.id)} for ct in action_cts],
        {'type': 'contact_persons', 'value': None},
    ]
    main_blocks_bottom = [
        {'type': 'related_actions', 'value': None},
        {'type': 'related_indicators', 'value': None},
    ]
    blocks = [
        ('details_main_top', ActionMainContentBlock, main_blocks_top),
        ('details_aside', ActionAsideContentBlock, aside_blocks),
        ('details_main_bottom', ActionMainContentBlock, main_blocks_bottom),
    ]
    out = {}
    for field_name, kls, data in blocks:
        blk = kls()
        val = blk.clean(blk.to_python(data))
        out[field_name] = val
    return out


def get_default_action_filter_blocks(plan: Plan) -> dict[str, blocks.StreamValue]:
    filter_blocks: list[dict[str, Any]] = [
        {'type': 'responsible_party', 'value': None},
        {'type': 'implementation_phase', 'value': None},
        {'type': 'schedule', 'value': None},
    ]

    ignore_cts = []
    out = {}
    if plan.secondary_action_classification is not None:
        ct = plan.secondary_action_classification
        f = {'type': 'category', 'value': {'style': 'buttons', 'category_type': ct.id}}
        blk = ActionListFilterBlock()
        out['primary_filters'] = blk.clean(blk.to_python([f]))
        ignore_cts.append(ct)

    if plan.primary_action_classification is not None:
        ct = plan.primary_action_classification
        f = {'type': 'category', 'value': {'style': 'dropdown', 'category_type': ct.id}}
        filter_blocks.append(f)
        ignore_cts.append(ct)

    action_cts = CategoryType.objects.filter(plan=plan, usable_for_actions=True)
    for ct in action_cts:
        if ct in ignore_cts:
            continue
        f = {'type': 'category', 'value': {'style': 'dropdown', 'category_type': ct.id}}
        filter_blocks.append(f)

    action_ats: AttributeTypeQuerySet = AttributeType.objects.for_actions(plan)
    for atype in action_ats:
        if atype.format not in (
                atype.AttributeFormat.UNORDERED_CHOICE,
                atype.AttributeFormat.ORDERED_CHOICE,
                atype.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT):
            continue
        f = {'type': 'attribute', 'value': {'attribute_type': atype.id}}
        filter_blocks.append(f)

    blk = ActionListFilterBlock()
    out['main_filters'] = blk.clean(blk.to_python(filter_blocks))
    return out


@register_streamfield_block
class RelatedPlanListBlock(blocks.StaticBlock):  # type: ignore[misc]
    class Meta:
        label = _('Related plans')
