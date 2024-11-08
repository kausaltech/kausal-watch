from __future__ import annotations

from aplans.field_registry import ModelFieldProperties as Properties, ModelFieldRegistry

from .models.action import Action

action_registry = ModelFieldRegistry(Action)

field = Properties

action_registry.register_all(
    field(
        field_name='responsible_parties',
        field_type='ManyToOneRel',
        report_block_class='reports.blocks.action_content.ActionResponsiblePartyReportFieldBlock',
        report_formatter_class='reports.report_formatters.ActionResponsiblePartyReportFieldFormatter',
        # force default
        # dashboard_column_block_class='actions.blocks.action_dashboard.ResponsiblePartiesColumnBlock',
    ),
    field(
        field_name='tasks',
        field_type='ManyToOneRel',
        report_formatter_class='reports.report_formatters.ActionTasksFormatter',
        dashboard_column_block_class='actions.blocks.action_dashboard.TasksColumnBlock',
    ),
    field(
        field_name='categories',
        field_type='ManyToManyField',
        report_block_class='reports.blocks.action_content.ActionCategoryReportFieldBlock',
        report_formatter_class='reports.report_formatters.ActionCategoryReportFieldFormatter',
        has_dashboard_column_block=False,
    ),
    field(
        field_name='dependencies',
        field_type='Custom',
        has_report_block=False,
        has_dashboard_column_block=False,
        has_details_block=True,
    ),
    field(
        field_name='attribute',
        field_type='Custom',
        has_report_block=True,
        has_dashboard_column_block=False,
        has_details_block=True,
        details_block_class='actions.blocks.action_content.ActionContentAttributeTypeBlock',
        report_block_class='reports.blocks.action_content.ActionAttributeTypeReportFieldBlock',
        report_formatter_class='reports.report_formatters.ActionAttributeTypeReportFieldFormatter',
    ),
)
