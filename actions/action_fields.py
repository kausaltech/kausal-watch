"""
Specify the block configurations for all the action fields.

This module only needs to contain custom configurations for actions fields which
need custom classes and/or parameters to be used in the blocks. All of the default
field block classes are automatically generated based on model introspection.

We generate default implementations or configure custom implementations
for blocks to be used in:
    - The action details page
    - The action dashboard table columns
    - The action excel report types

In the end, we would like these different blocks to share as much of the implementation
as possible with each other.
"""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from kausal_common.blocks.registry import FieldBlockContext, FieldContextConfig, ModelFieldProperties, ModelFieldRegistry

from actions.blocks.base import ActionColumnBlock, ActionContentBlockBase, ActionFilterBlock

from .blocks import generated
from .models.action import Action

action_registry = ModelFieldRegistry(
    model=Action,
    target_module=generated,
    contexts=[
        FieldContextConfig(
            context=FieldBlockContext.DASHBOARD,
            autogen_prefix='',
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
        )
    ]
)


def register(field: ModelFieldProperties):
    action_registry.register(field)

Field = ModelFieldProperties

def initialize():
    # The following fields will have no blocks created for them whatsoever
    action_registry.disable_fields(
        'completion', 'date_format', 'decision_level', 'dependency_role', 'dependent_relationships', 'id', 'impact_groups',
        'indicators', 'merged_with', 'monitoring_quality_points', 'order', 'plan', 'status_updates',
        'superseded_actions', 'superseded_by', 'copies', 'copy_of', 'uuid', 'visibility',
    )

    register(Field(
        field_name='responsible_parties',
        field_type='many',
        report_block_class='reports.blocks.action_content.ActionResponsiblePartyReportFieldBlock',
        report_formatter_class='reports.report_formatters.ActionResponsiblePartyReportFieldFormatter',
        details_block_class='actions.blocks.action_content_blocks.ActionResponsiblePartiesBlock',
    ))
    register(Field(
        field_name='tasks',
        field_type='many',
        report_formatter_class='reports.report_formatters.ActionTasksFormatter',
    ))
    register(Field(
        field_name='categories',
        field_type='many',
        report_block_class='reports.blocks.action_content.ActionCategoryReportFieldBlock',
        report_formatter_class='reports.report_formatters.ActionCategoryReportFieldFormatter',
        has_dashboard_column_block=False,
        details_block_class='actions.blocks.action_content_blocks.ActionContentCategoryTypeBlock',
    ))
    register(Field(
        field_name='dependencies',
        field_type='custom',
        has_report_block=False,
        has_dashboard_column_block=False,
        has_details_block=True,
        custom_label=_('Action dependencies'),
    ))
    register(Field(
        field_name='attribute',
        field_type='custom',
        has_report_block=True,
        has_dashboard_column_block=True,
        has_details_block=True,
        details_block_class='actions.blocks.action_content_blocks.ActionContentAttributeTypeBlock',
        report_block_class='reports.blocks.action_content.ActionAttributeTypeReportFieldBlock',
        report_formatter_class='reports.report_formatters.ActionAttributeTypeReportFieldFormatter',
        dashboard_column_block_class='actions.blocks.action_dashboard.FieldColumnBlock',
    ))
    register(Field(
        field_name='official_name',
        details_block_class='actions.blocks.action_content_blocks.ActionOfficialNameBlock',
        has_dashboard_column_block=False,
        has_report_block=False,
    ))
    register(Field(
        field_name='primary_org',
        field_type='single',
        has_dashboard_column_block=True,
        dashboard_column_block_class_name='OrganizationColumnBlock',
        has_details_block=False,
        report_formatter_class='reports.report_formatters.ActionSingleRelatedModelFieldFormatter',
    ))
    register(Field(
        field_name='related_indicators',
        field_type='many',
        dashboard_column_block_class_name='IndicatorsColumnBlock',
        report_formatter_class='reports.report_formatters.ActionIndicatorsFormatter',
    ))
    register(Field(
        field_name='merged_actions',
        field_type='many',
        custom_label=_('Merged actions'),
        has_dashboard_column_block=False,
        has_report_block=False,
    ))
    register(Field(
        field_name='lead_paragraph',
        field_type='primitive',
        has_dashboard_column_block=False,
        has_report_block=False,
    ))
    for field_name in ['contact_persons', 'links', 'related_actions', 'schedule']:
        register(Field(
            field_name,
            field_type='many',
            has_dashboard_column_block=False,
            has_report_block=False,
        ))
    for field_name in ['start_date', 'end_date']:
        register(Field(
            field_name,
            has_details_block=False,
            has_report_block=True,
            report_formatter_class='reports.report_formatters.ActionDateFieldFormatter',
        ))
    register(Field(
        field_name='schedule_continuous',
        has_details_block=False,
    ))
    register(Field(
        field_name='updated_at',
        has_details_block=False,
        has_report_block=True,
        report_formatter_class='reports.report_formatters.ActionDateTimeFieldFormatter',
    ))
    register(Field(
        field_name='manual_status_reason',
        has_details_block=False,
        has_dashboard_column_block=False,
    ))
    register(Field(
        field_name='implementation_phase',
        field_type='single',
        has_details_block=False,
        report_block_class='reports.blocks.action_content.ActionImplementationPhaseReportFieldBlock',
        report_formatter_class='reports.report_formatters.ActionImplementationPhaseReportFieldFormatter'
    ))
    register(Field(
        field_name='status',
        field_type='single',
        has_details_block=False,
        report_block_class='reports.blocks.action_content.ActionStatusReportFieldBlock',
        report_formatter_class='reports.report_formatters.ActionStatusReportFieldFormatter'
    ))
    for field_name in ['name', 'identifier']:
        register(Field(
            field_name,
            field_type='primitive',
            has_details_block=False,
        ))
    register(Field(
        field_name='description',
        has_dashboard_column_block=False,
    ))
    action_registry.finalize()


initialize()
