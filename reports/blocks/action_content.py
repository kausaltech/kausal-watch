from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.admin.panels import HelpPanel

from grapple.helpers import register_streamfield_block

#from actions.blocks.action_content import get_action_block_for_field
from actions.blocks.choosers import ActionAttributeTypeChooserBlock, CategoryLevelChooserBlock, CategoryTypeChooserBlock
from reports import report_formatters as formatters
from reports.report_formatters import ActionReportContentField

if TYPE_CHECKING:
    from django.db.models import Model


class FieldBlockWithHelpPanel(ActionReportContentField):
    def get_help_label(self, value: Model):
        return None

    def get_help_panel(self, block_value, snapshot):
        value = self.value_for_action_snapshot(block_value, snapshot) or ''
        if not isinstance(value, Iterable) or isinstance(value, str):
            value = [value]
        value = "; ".join(str(v) for v in value)
        label = self.get_help_label(block_value)
        if label is None:
            label = self.label
        heading = f'{label} ({snapshot.report})'
        return HelpPanel(value, heading=heading)


@register_streamfield_block
class ActionAttributeTypeReportFieldBlock(blocks.StructBlock, FieldBlockWithHelpPanel):
    attribute_type = ActionAttributeTypeChooserBlock(required=True)

    def get_report_value_formatter_class(self):
        return formatters.ActionAttributeTypeReportFieldFormatter

    def get_help_label(self, value):
        if 'attribute_type' in value:
            at = value.get('attribute_type')
            if hasattr(at, 'name_i18n'):
                return at.name_i18n
        return None

    class Meta:
        label = _("Action field")


@register_streamfield_block
class ActionCategoryReportFieldBlock(blocks.StructBlock, FieldBlockWithHelpPanel):
    category_type = CategoryTypeChooserBlock(required=True)
    category_level = CategoryLevelChooserBlock(required=False)

    def get_report_value_formatter_class(self):
        return formatters.ActionCategoryReportFieldFormatter

    class Meta:
        label = _("Action category")


@register_streamfield_block
class ActionImplementationPhaseReportFieldBlock(blocks.StaticBlock, FieldBlockWithHelpPanel):
    def get_report_value_formatter_class(self):
        return formatters.ActionImplementationPhaseReportFieldFormatter

    class Meta:
        label = _("Implementation phase")


@register_streamfield_block
class ActionStatusReportFieldBlock(blocks.StaticBlock, FieldBlockWithHelpPanel):
    def get_report_value_formatter_class(self):
        return formatters.ActionStatusReportFieldFormatter

    class Meta:
        label = _("Status")


@register_streamfield_block
class ActionResponsiblePartyReportFieldBlock(blocks.StructBlock, FieldBlockWithHelpPanel):
    # FIXME: Note that this block is currently actually exporting only the primary
    # responsible parties. That's why the label is set accordingly.
    # There should be a field to configure which role(s) should
    # be exported and that should affect the label(s)

    target_ancestor_depth = blocks.IntegerBlock(
        label=_('Level of containing organization'),
        required=False,
        max_value=10,
        min_value=1,
        help_text=_(
            'In addition to the organization itself, an organizational unit containing the organization '
            'is included in the report. Counting from the top-level root organisation at level 1, which level '
            'in the organizational hierarchy should be used to find this containing organization? '
            'If left empty, don\'t add the containing organization to the report.',
        ),
    )

    def get_report_value_formatter_class(self):
        return formatters.ActionResponsiblePartyReportFieldFormatter

    class Meta:
        label = _("Primary responsible party")


"""
We are reusing generated action field block classes from the action app

If adding reporting support for a block, the block should be explicitly added here
and correct report generation should be verified.
"""
from actions.action_fields import action_registry
ActionDescriptionBlock = action_registry.get_report_block_class('description')
ActionManualStatusReasonBlock = action_registry.get_report_block_class('manual_status_reason')
ActionTasksBlock = action_registry.get_report_block_class('tasks')


@register_streamfield_block
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
