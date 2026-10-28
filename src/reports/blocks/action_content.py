from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block

from kausal_common.blocks.registry import FieldBlockContext

from actions.blocks.base import ActionReportContentField
from actions.blocks.choosers import ActionAttributeTypeChooserBlock, CategoryLevelChooserBlock, CategoryTypeChooserBlock
from actions.blocks.stream_block import generate_stream_block
from reports import report_formatters as formatters


@register_streamfield_block
class ActionAttributeTypeReportFieldBlock(ActionReportContentField):
    attribute_type = ActionAttributeTypeChooserBlock(required=True)

    def get_report_value_formatter_class(self):
        return formatters.ActionAttributeTypeReportFieldFormatter

    class Meta:
        label = _('Action field')


@register_streamfield_block
class ActionCategoryReportFieldBlock(ActionReportContentField):
    category_type = CategoryTypeChooserBlock(required=True)
    category_level = CategoryLevelChooserBlock(required=False)

    def get_report_value_formatter_class(self):
        return formatters.ActionCategoryReportFieldFormatter

    class Meta:
        label = _('Action category')


@register_streamfield_block
class ActionImplementationPhaseReportFieldBlock(ActionReportContentField):
    def get_report_value_formatter_class(self):
        return formatters.ActionImplementationPhaseReportFieldFormatter

    class Meta:
        label = _('Implementation phase')
        field_name = 'implementation_phase'


@register_streamfield_block
class ActionStatusReportFieldBlock(ActionReportContentField):
    def get_report_value_formatter_class(self):
        return formatters.ActionStatusReportFieldFormatter

    class Meta:
        label = _('Status')


@register_streamfield_block
class ActionResponsiblePartyReportFieldBlock(ActionReportContentField):
    # FIXME: Note that this block is currently actually exporting only the primary
    # responsible parties. That's why the label is set accordingly.
    # There should be a field to configure which role(s) should
    # be exported and that should affect the label(s)

    target_ancestor_depth: blocks.IntegerBlock = blocks.IntegerBlock(
        label=_('Level of containing organization'),
        required=False,
        max_value=10,
        min_value=1,
        help_text=_(
            'In addition to the organization itself, an organizational unit containing the organization '
            'is included in the report. Counting from the top-level root organisation at level 1, which level '
            'in the organizational hierarchy should be used to find this containing organization? '
            "If left empty, don't add the containing organization to the report.",
        ),
    )

    def get_report_value_formatter_class(self):
        return formatters.ActionResponsiblePartyReportFieldFormatter

    class Meta:
        label = _('Primary responsible party')
        field_name = 'primary_org'
        default = {'target_ancestor_depth': None}


"""
Whenever possible, try to use the existing report block classes
that can be retrieved from the action_registry simply with the
field name, instead of implenting a custom ReportFieldBlock from scratch.
"""
ReportFieldBlock = generate_stream_block(
    'ReportFieldBlock',
    fields=(
        'implementation_phase',
        'attribute',
        'responsible_parties',
        'categories',
        'status',
        'manual_status_reason',
        'description',
        'tasks',
        'start_date',
        'end_date',
        'schedule_continuous',
        'updated_at',
        'related_indicators',
        'primary_org',
    ),
    support_editing_from_other_form=False,
    block_context=FieldBlockContext.REPORT,
)
