from __future__ import annotations  # noqa: I001

from django.utils.translation import gettext_lazy as _

from wagtail import blocks

import pytest

from actions.blocks.base import ActionColumnBlock, ActionContentBlockBase
from kausal_common.blocks.registry import FieldBlockContext, FieldContextConfig, ModelFieldProperties, ModelFieldRegistry

from actions.blocks import generated
from actions.blocks.stream_block import generate_stream_block
from actions.models import Action

from actions.blocks.action_content_blocks import (
    ActionContactFormBlock,
    ActionContentAttributeTypeBlock,
    ActionContentCategoryTypeBlock,
    IndicatorCausalChainBlock,
    PlanDatasetsBlock,
)
from reports.blocks.report_comparison_block import ReportComparisonBlock

from actions.blocks.action_content import (
    ActionContentSectionBlock,
)
from reports.blocks.action_content import (
    ActionAttributeTypeReportFieldBlock,
    ActionCategoryReportFieldBlock,
    ActionImplementationPhaseReportFieldBlock,
    ActionResponsiblePartyReportFieldBlock,
    ActionStatusReportFieldBlock,
)


@pytest.fixture
def populated_action_registry():
    action_registry = ModelFieldRegistry(
        model=Action,
        target_module=generated,
        contexts=[
            FieldContextConfig(
                context=FieldBlockContext.DASHBOARD,
                block_base_class=ActionColumnBlock,
            ),
            FieldContextConfig(
                context=FieldBlockContext.REPORT,
                block_base_class=ActionContentBlockBase,
            ),
        ],
    )

    def report():  # noqa: ANN202
        from reports.blocks import action_content

        return action_content

    def register(*field_names, **kwargs):  # noqa: ANN202
        for field_name in field_names:
            action_registry.register(
                ModelFieldProperties(field_name=field_name, **kwargs),
            )

    action_registry.disable_fields(
        'completion',
        'date_format',
        'decision_level',
        'dependency_role',
        'dependent_relationships',
        'id',
        'impact_groups',
        'indicators',
        'merged_with',
        'monitoring_quality_points',
        'order',
        'plan',
        'schedule_continuous',
        'status_updates',
        'superseded_actions',
        'superseded_by',
        'copies',
        'copy_of',
        'uuid',
        'visibility',
    )

    register(
        'responsible_parties',
        field_type='many',
        report_block_class=lambda: report().ActionResponsiblePartyReportFieldBlock,
        report_formatter_class='reports.report_formatters.ActionResponsiblePartyReportFieldFormatter',
        details_block_class='actions.blocks.action_content_blocks.ActionResponsiblePartiesBlock',
    )
    register(
        'tasks',
        field_type='many',
        report_formatter_class='reports.report_formatters.ActionTasksFormatter',
    )
    register(
        'categories',
        field_type='many',
        report_block_class=lambda: report().ActionCategoryReportFieldBlock,
        report_formatter_class='reports.report_formatters.ActionCategoryReportFieldFormatter',
        has_dashboard_column_block=False,
        details_block_class='actions.blocks.action_content_blocks.ActionContentCategoryTypeBlock',
    )
    register(
        'dependencies',
        field_type='custom',
        has_report_block=False,
        has_dashboard_column_block=False,
        has_details_block=True,
        custom_label=_('Action dependencies'),
    )
    register(
        'attribute',
        field_type='custom',
        has_report_block=True,
        has_dashboard_column_block=True,
        has_details_block=True,
        details_block_class='actions.blocks.action_content_blocks.ActionContentAttributeTypeBlock',
        report_block_class=lambda: report().ActionAttributeTypeReportFieldBlock,
        report_formatter_class='reports.report_formatters.ActionAttributeTypeReportFieldFormatter',
        dashboard_column_block_class='actions.blocks.action_dashboard.FieldColumnBlock',
    )
    register(
        'official_name',
        details_block_class='actions.blocks.action_content_blocks.ActionOfficialNameBlock',
        has_dashboard_column_block=False,
        has_report_block=False,
    )
    register(
        'primary_org',
        field_type='single',
        has_dashboard_column_block=True,
        dashboard_column_block_class_name='OrganizationColumnBlock',
        has_details_block=False,
        has_report_block=False,
    )
    register(
        'related_indicators',
        field_type='many',
        dashboard_column_block_class_name='IndicatorsColumnBlock',
        has_report_block=False,
    )
    register(
        'merged_actions',
        field_type='many',
        custom_label=_('Merged actions'),
        has_dashboard_column_block=False,
        has_report_block=False,
    )
    register(
        'lead_paragraph',
        field_type='primitive',
        has_dashboard_column_block=False,
        has_report_block=False,
    )
    register(
        'contact_persons',
        'links',
        'related_actions',
        'schedule',
        field_type='many',
        has_dashboard_column_block=False,
        has_report_block=False,
    )
    register(
        'start_date',
        'end_date',
        'identifier',
        'updated_at',
        'name',
        has_details_block=False,
        has_report_block=False,
    )
    register(
        'manual_status_reason',
        has_details_block=False,
        has_dashboard_column_block=False,
    )
    register(
        'status',
        'implementation_phase',
        field_type='single',
        has_details_block=False,
    )
    register(
        'description',
        has_dashboard_column_block=False,
    )
    return action_registry


@pytest.fixture
def generated_block_class(populated_action_registry):
    def get(name, block_context):  # noqa: ANN202
        return populated_action_registry.get_block(block_context, name)

    return get


@pytest.fixture
def action_content_section_element_block():
    ActionContentSectionElementBlock = generate_stream_block(
        'ActionMainContentSectionElementBlock',
        fields=(
            ('attribute', ActionContentAttributeTypeBlock()),
            ('categories', ActionContentCategoryTypeBlock()),
        ),
    )
    return ActionContentSectionElementBlock


@pytest.fixture
def action_main_content_block():
    ActionMainContentBlock = generate_stream_block(
        'ActionMainContentBlock',
        fields=(
            ('section', ActionContentSectionBlock(required=True)),
            'lead_paragraph',
            'description',
            'official_name',
            'attribute',
            'categories',
            'links',
            'tasks',
            'merged_actions',
            'related_actions',
            'dependencies',
            'related_indicators',
            ('contact_form', ActionContactFormBlock(required=True)),
            ('report_comparison', ReportComparisonBlock()),
            ('indicator_causal_chain', IndicatorCausalChainBlock()),
            ('datasets', PlanDatasetsBlock()),
        ),
        support_editing_from_other_form=True,
    )

    return ActionMainContentBlock


@pytest.fixture
def action_aside_content_block():
    ActionAsideContentBlock = generate_stream_block(
        'ActionAsideContentBlock',
        fields=[
            'schedule',
            'contact_persons',
            'responsible_parties',
            'attribute',
            'categories',
        ],
        support_editing_from_other_form=True,
    )
    return ActionAsideContentBlock


@pytest.fixture
def action_dashboard_column_block():
    ActionDashboardColumnBlock = generate_stream_block(
        'ActionDashboardColumnBlock',
        fields=(
            'identifier',
            'name',
            'implementation_phase',
            'status',
            'tasks',
            'responsible_parties',
            'updated_at',
            'start_date',
            'end_date',
            'attribute',
            'related_indicators',
            'primary_org',
        ),
        support_editing_from_other_form=False,
        block_context=FieldBlockContext.DASHBOARD,
    )
    return ActionDashboardColumnBlock


@pytest.fixture
def report_field_block(populated_action_registry):
    ActionDescriptionBlock = populated_action_registry.get_block_class('report', 'description')
    ActionManualStatusReasonBlock = populated_action_registry.get_block_class('report', 'manual_status_reason')
    ActionTasksBlock = populated_action_registry.get_block_class('report', 'tasks')

    class ReportFieldBlock(blocks.StreamBlock):
        # All blocks mentioned here must have a formatter which implements
        # xlsx_column_labels, value_for_action and value_for_action_snapshot
        implementation_phase = ActionImplementationPhaseReportFieldBlock()
        attribute_type = ActionAttributeTypeReportFieldBlock()
        responsible_party = ActionResponsiblePartyReportFieldBlock()
        category = ActionCategoryReportFieldBlock()
        status = ActionStatusReportFieldBlock()
        manual_status_reason = ActionManualStatusReasonBlock()
        description = ActionDescriptionBlock()
        tasks = ActionTasksBlock()

        graphql_types = [
            ActionImplementationPhaseReportFieldBlock,
            ActionAttributeTypeReportFieldBlock,
            ActionResponsiblePartyReportFieldBlock,
            ActionCategoryReportFieldBlock,
            ActionStatusReportFieldBlock,
            ActionManualStatusReasonBlock,
            ActionDescriptionBlock,
            ActionTasksBlock,
        ]

    return ReportFieldBlock
