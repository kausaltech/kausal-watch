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

from aplans.field_registry import ModelFieldProperties, ModelFieldRegistry

from .models.action import Action

action_registry = ModelFieldRegistry(Action)

def register(*field_names, **kwargs):
    for field_name in field_names:
        action_registry.register(
            ModelFieldProperties(field_name=field_name, **kwargs, model=Action),
        )

def initialize():
    # The following fields will have no blocks created for them whatsoever
    action_registry.disable_fields(
        'completion', 'date_format', 'decision_level', 'dependency_role', 'dependent_relationships', 'id', 'impact', 'impact_groups',
        'indicators', 'merged_with', 'monitoring_quality_points', 'order', 'plan', 'schedule_continuous', 'status_updates',
        'superseded_actions', 'superseded_by', 'uuid', 'visibility',
    )

    register(
        'responsible_parties',
        field_type='ManyToOneRel',
        report_block_class='reports.blocks.action_content.ActionResponsiblePartyReportFieldBlock',
        report_formatter_class='reports.report_formatters.ActionResponsiblePartyReportFieldFormatter',
        details_block_class='actions.blocks.action_content_blocks.ActionResponsiblePartiesBlock',
    )
    register(
        'tasks',
        field_type='ManyToOneRel',
        report_formatter_class='reports.report_formatters.ActionTasksFormatter',
        dashboard_column_block_class='actions.blocks.action_dashboard.TasksColumnBlock',
    )
    register(
        'categories',
        field_type='ManyToManyField',
        report_block_class='reports.blocks.action_content.ActionCategoryReportFieldBlock',
        report_formatter_class='reports.report_formatters.ActionCategoryReportFieldFormatter',
        has_dashboard_column_block=False,
        details_block_class='actions.blocks.action_content_blocks.ActionContentCategoryTypeBlock',
    )
    register(
        'dependencies',
        field_type='Custom',
        has_report_block=False,
        has_dashboard_column_block=False,
        has_details_block=True,
        custom_label=_('Action dependencies'),
    )
    register(
        'attribute',
        field_type='Custom',
        has_report_block=True,
        has_dashboard_column_block=True,
        has_details_block=True,
        details_block_class='actions.blocks.action_content_blocks.ActionContentAttributeTypeBlock',
        report_block_class='reports.blocks.action_content.ActionAttributeTypeReportFieldBlock',
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
        has_dashboard_column_block=True,
        dashboard_column_block_class_name='OrganizationColumnBlock',
        has_details_block=False,
        has_report_block=False,
    )
    register(
        'related_indicators',
        dashboard_column_block_class_name='InidicatorsColumnBlock',
        has_report_block=False,
    )
    register(
        'merged_actions',
        custom_label=_('Merged actions'),
        has_dashboard_column_block=False,
        has_report_block=False,
    )
    register(
        'contact_persons',
        'lead_paragraph',
        'links',
        'related_actions',
        'schedule',
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
        has_details_block=False,
    )

    action_registry.update_with_defaults()

initialize()
