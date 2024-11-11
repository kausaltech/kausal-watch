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

def register(field_name, **kwargs):
    action_registry.register(
        ModelFieldProperties(field_name=field_name, **kwargs, model=Action),
    )

# The following fields will have no blocks created for them whatsoever
action_registry.disable_fields(
    'completion',
    'date_format',
    'decision_level',
    'dependency_role',
    'dependent_relationships',
    'id',
    'impact',
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
    'uuid',
    'visibility',
)

register(
    'responsible_parties',
    field_type='ManyToOneRel',
    report_block_class='reports.blocks.action_content.ActionResponsiblePartyReportFieldBlock',
    report_formatter_class='reports.report_formatters.ActionResponsiblePartyReportFieldFormatter',
    details_block_class='actions.blocks.action_content.ActionResponsiblePartiesBlock',
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
    details_block_class='actions.blocks.action_content.ActionOfficialNameBlock',
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
    details_block_class='actions.blocks.action_content.ActionContentAttributeTypeBlock',
    report_block_class='reports.blocks.action_content.ActionAttributeTypeReportFieldBlock',
    report_formatter_class='reports.report_formatters.ActionAttributeTypeReportFieldFormatter',
    dashboard_column_block_class='actions.blocks.action_dashboard.FieldColumnBlock',
)
register(
    'merged_actions',
    custom_label=_('Merged actions'),
    has_dashboard_column_block=False,
    has_report_block=False,
)
register(
    'official_name',
    details_block_class='actions.blocks.action_content.ActionOfficialNameBlock',
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
    'contact_persons',
    has_dashboard_column_block=False,
    has_report_block=False,
)
register(
    'lead_paragraph',
    has_dashboard_column_block=False,
    has_report_block=False,
)
register(
    'links',
    has_dashboard_column_block=False,
    has_report_block=False,
)
register(
    'related_actions',
    has_dashboard_column_block=False,
    has_report_block=False,
)
register(
    'schedule',
    has_dashboard_column_block=False,
    has_report_block=False,
)
register(
    'start_date',
    has_details_block=False,
    has_report_block=False,
)
register(
    'end_date',
    has_details_block=False,
    has_report_block=False,
)
register(
    'identifier',
    has_details_block=False,
    has_report_block=False,
)
register(
    'implementation_phase',
    has_details_block=False,
)
register(
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
    has_details_block=False,
)
register(
    'updated_at',
    has_details_block=False,
    has_report_block=False,
)


action_registry.update_with_defaults()
is_valid = action_registry.is_valid()
