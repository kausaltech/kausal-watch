from __future__ import annotations

import importlib
import inspect

from wagtail.blocks import Block, StreamBlock, StructBlock

import pytest

from kausal_common.blocks.registry import FieldBlockContext, FieldContextConfig, ModelFieldProperties, ModelFieldRegistry

from actions.blocks.action_content import (
    ActionContactFormBlock,
    ActionContentAttributeTypeBlock,
    ActionContentCategoryTypeBlock,
    ActionContentSectionBlock,
    ActionOfficialNameBlock,
    ActionResponsiblePartiesBlock,
    IndicatorCausalChainBlock,
    PlanDatasetsBlock,
    ReportComparisonBlock,
)
from actions.blocks.action_dashboard import (
    FieldColumnBlock,
)
from actions.blocks.base import (
    ActionColumnBlock,
    ActionContentBlockBase,
    ActionFilterBlock,
    ActionListContentBlock,
    ActionReportContentField,
)
from actions.blocks.mixins import (
    ActionListPageBlockPresenceMixin,
)
from actions.blocks.stream_block import generate_stream_block
from actions.models import Action
from reports.blocks.action_content import (
    ActionAttributeTypeReportFieldBlock,
    ActionCategoryReportFieldBlock,
    ActionImplementationPhaseReportFieldBlock,
    ActionResponsiblePartyReportFieldBlock,
    ActionStatusReportFieldBlock,
)

from .fixtures_stream_block import *

pytest.mark.django_db  # noqa: B018


@pytest.mark.parametrize(
    ('fixturename', 'expected_base_classes'),
    [
        ('action_content_section_element_block', tuple()),
        ('action_dashboard_column_block', tuple()),
        ('report_field_block', tuple()),
        ('action_main_content_block', (ActionListPageBlockPresenceMixin,)),
        ('action_aside_content_block', (ActionListPageBlockPresenceMixin,)),
    ],
)
def test_expected_base_classes(fixturename, expected_base_classes, request):
    b = request.getfixturevalue(fixturename)
    for c in expected_base_classes + (StreamBlock,):
        assert c in inspect.getmro(b)


EXPECTED_SUBBLOCK_BASES = {
    'action_content_section_element_block': (),
    'action_dashboard_column_block': (
        StructBlock,
        ActionColumnBlock,
    ),
    'report_field_block': (
        StructBlock,
        ActionListContentBlock,
        ActionReportContentField,
    ),
    'action_main_content_block': (
        StructBlock,
        ActionListContentBlock,
        ActionReportContentField,
    ),
    'action_aside_content_block': (
        StructBlock,
        ActionListContentBlock,
        ActionReportContentField,
    ),
}


@pytest.mark.parametrize(
    ('fixturename', 'expected_subblocks'),
    [
        (
            'action_content_section_element_block',
            [
                ('attribute', ActionContentAttributeTypeBlock),
                ('categories', ActionContentCategoryTypeBlock),
            ],
        ),
        (
            'action_dashboard_column_block',
            [
                ('identifier'),
                ('name'),
                ('implementation_phase'),
                ('status'),
                ('tasks'),
                ('responsible_parties'),
                ('related_indicators'),
                ('updated_at'),
                ('start_date'),
                ('end_date'),
                ('primary_org'),
                ('attribute', FieldColumnBlock),
            ],
        ),
        (
            'report_field_block',
            [
                ('implementation_phase', ActionImplementationPhaseReportFieldBlock),
                ('attribute_type', ActionAttributeTypeReportFieldBlock),
                ('responsible_party', ActionResponsiblePartyReportFieldBlock),
                ('category', ActionCategoryReportFieldBlock),
                ('status', ActionStatusReportFieldBlock),
                ('manual_status_reason'),
                ('description'),
                ('tasks'),
            ],
        ),
        (
            'action_main_content_block',
            [
                ('section', ActionContentSectionBlock),
                ('official_name', ActionOfficialNameBlock),
                ('attribute', ActionContentAttributeTypeBlock),
                ('categories', ActionContentCategoryTypeBlock),
                ('contact_form', ActionContactFormBlock),
                ('report_comparison', ReportComparisonBlock),
                ('indicator_causal_chain', IndicatorCausalChainBlock),
                ('datasets', PlanDatasetsBlock),
                ('lead_paragraph'),
                ('description'),
                ('links'),
                ('tasks'),
                ('merged_actions'),
                ('related_actions'),
                ('dependencies'),
                ('related_indicators'),
            ],
        ),
        (
            'action_aside_content_block',
            [
                ('responsible_parties', ActionResponsiblePartiesBlock),
                ('attribute', ActionContentAttributeTypeBlock),
                ('categories', ActionContentCategoryTypeBlock),
                ('schedule'),
                ('contact_persons'),
            ],
        ),
    ],
)
def test_expected_subblocks(fixturename, expected_subblocks, request, generated_block_class):
    b = request.getfixturevalue(fixturename)
    for c in expected_subblocks:
        block_class = None
        if isinstance(c, tuple):
            field_name, block_class = c
        else:
            field_name = c
        assert field_name in b.base_blocks
        if block_class:
            # The block is manually configured
            assert isinstance(b.base_blocks[field_name], block_class)
            assert block_class in b.graphql_types
            continue
        # The block is dynamically generated
        block = b.base_blocks[field_name]
        assert any(isinstance(block, t) for t in b.graphql_types)
        for base in EXPECTED_SUBBLOCK_BASES[fixturename]:
            assert base in inspect.getmro(type(block))


@pytest.fixture
def action_registry_factory():
    generated = importlib.import_module('actions.blocks.generated')

    def make_action_registry(*default_fields):
        mfr = ModelFieldRegistry(
            Action,
            generated,
            contexts=[
                FieldContextConfig(
                    context=FieldBlockContext.DASHBOARD,
                    block_base_class=ActionColumnBlock,
                ),
                FieldContextConfig(
                    context=FieldBlockContext.REPORT,
                    block_base_class=ActionContentBlockBase,
                ),
                FieldContextConfig(
                    context=FieldBlockContext.DETAILS,
                    block_base_class=ActionContentBlockBase,
                ),
                FieldContextConfig(
                    context=FieldBlockContext.LIST_FILTERS,
                    block_base_class=ActionFilterBlock,
                ),
            ],
        )
        for f in default_fields:
            mfr.register(ModelFieldProperties(field_name=f))
        return mfr

    return make_action_registry


def test_generate_stream_block_string_field(action_registry_factory):
    action_registry = action_registry_factory('name')
    stream_block_class = generate_stream_block(
        'ClassName',
        fields=['name'],
        action_registry=action_registry,
    )
    assert isinstance(stream_block_class.base_blocks['name'], Block)


def test_generate_stream_block_tuple_field(action_registry_factory):
    class FooBar(StructBlock):
        pass

    action_registry = action_registry_factory('name')
    stream_block_class = generate_stream_block(
        'ClassName',
        fields=[('name', FooBar())],
        action_registry=action_registry,
    )
    isinstance(stream_block_class.base_blocks['name'], FooBar)
