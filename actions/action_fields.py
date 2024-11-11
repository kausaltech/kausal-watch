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

def register(**kwargs):
    action_registry.register(
        ModelFieldProperties(**kwargs, model=Action),
    )
    action_registry.update_with_defaults()


register(
    field_name='responsible_parties',
    field_type='ManyToOneRel',
    report_block_class='reports.blocks.action_content.ActionResponsiblePartyReportFieldBlock',
    report_formatter_class='reports.report_formatters.ActionResponsiblePartyReportFieldFormatter',
    details_block_class='actions.blocks.action_content.ActionResponsiblePartiesBlock',
    # force default
    # dashboard_column_block_class='actions.blocks.action_dashboard.ResponsiblePartiesColumnBlock',
)

register(
    field_name='tasks',
    field_type='ManyToOneRel',
    report_formatter_class='reports.report_formatters.ActionTasksFormatter',
    dashboard_column_block_class='actions.blocks.action_dashboard.TasksColumnBlock',
)

register(
    field_name='categories',
    field_type='ManyToManyField',
    report_block_class='reports.blocks.action_content.ActionCategoryReportFieldBlock',
    report_formatter_class='reports.report_formatters.ActionCategoryReportFieldFormatter',
    has_dashboard_column_block=False,
    details_block_class='actions.blocks.action_content.ActionOfficialNameBlock',
)

register(
    field_name='dependencies',
    field_type='Custom',
    has_report_block=False,
    has_dashboard_column_block=False,
    has_details_block=True,
    custom_label=_('Action dependencies'),
)

register(
    field_name='attribute',
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
    field_name='merged_actions',
    custom_label=_('Merged actions'),
    has_dashboard_column_block=False,
)

register(
    field_name='official_name',
    details_block_class='actions.blocks.action_content.ActionOfficialNameBlock',
    has_dashboard_column_block=False,
)

register(
    field_name='primary_org',
    has_dashboard_column_block=True,
    dashboard_column_block_class_name='OrganizationColumnBlock',
)

is_valid = action_registry.is_valid()
