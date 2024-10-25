from __future__ import annotations

from aplans.field_registry import ModelFieldProperties as Properties, ModelFieldRegistry

from .models.action import Action

action_registry = ModelFieldRegistry(Action)

action_registry.register_all(
    Properties(
        field_name='responsible_parties',
        field_type='ManyToOneRel',
        report_block_class='reports.blocks.action_content.ActionResponsiblePartyReportFieldBlock',
        dashboard_column_block_class='actions.blocks.action_dashboard.ResponsiblePartiesColumnBlock',
    ),
    Properties(
        field_name='tasks',
        field_type='ManyToOneRel',
        report_formatter_class='reports.report_formatters.ActionTasksFormatter',
        dashboard_column_block_class='actions.blocks.action_dashboard.TasksColumnBlock',
    ),
)
