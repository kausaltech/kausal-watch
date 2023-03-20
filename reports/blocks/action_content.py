from django.apps import apps
from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLField, GraphQLForeignKey, GraphQLString
from grapple.registry import registry as grapple_registry
from wagtail.admin.edit_handlers import HelpPanel
from wagtail.core import blocks

from actions.attributes import AttributeType
from actions.models import ActionImplementationPhase, AttributeType as AttributeTypeModel
from actions.blocks.choosers import ActionAttributeTypeChooserBlock
from reports.blocks.choosers import ReportTypeChooserBlock, ReportTypeFieldChooserBlock


@register_streamfield_block
class ReportComparisonBlock(blocks.StructBlock):
    report_type = ReportTypeChooserBlock(label=_('Report type'), required=True)
    report_field = ReportTypeFieldChooserBlock(label=_('UUID of report field'), required=True)

    def reports_to_compare(self, values):
        num_compare = 2  # TODO: Make this configurable in block
        report_type = values['report_type']
        reports = report_type.reports.order_by('-start_date')[:num_compare]
        return reports

    graphql_fields = [
        GraphQLForeignKey('report_type', 'reports.ReportType'),
        GraphQLString('report_field'),
        # For some reason GraphQLForeignKey strips the is_list argument, so we need to use GraphQLField directly here
        GraphQLField(
            'reports_to_compare',
            lambda: grapple_registry.models.get(apps.get_model('reports', 'Report')),
            is_list=True,
        ),
    ]


@register_streamfield_block
class ActionAttributeTypeReportFieldBlock(blocks.StructBlock):
    attribute_type = ActionAttributeTypeChooserBlock(required=True, label=_("Attribute type"))

    class Meta:
        label = _("Action attribute")

    graphql_fields = [
        GraphQLForeignKey('attribute_type', AttributeTypeModel, required=True)
    ]

    def get_report_export_column_label(self, block_value):
        wrapped_type = AttributeType.from_model_instance(block_value['attribute_type'])
        return wrapped_type.get_report_export_column_label()

    def get_report_export_value_for_action(self, block_value, action):
        wrapped_type = AttributeType.from_model_instance(block_value['attribute_type'])
        try:
            attribute = wrapped_type.get_attributes(action).get()
        except wrapped_type.ATTRIBUTE_MODEL.DoesNotExist:
            return None
        return str(attribute)

    def get_report_export_value_for_action_snapshot(self, block_value, snapshot):
        attribute = snapshot.get_attribute_for_type(block_value['attribute_type'])
        if attribute:
            return str(attribute)
        return None

    def add_xlsx_cell_format(self, block_value, workbook):
        wrapped_type = AttributeType.from_model_instance(block_value['attribute_type'])
        return wrapped_type.add_xlsx_cell_format(workbook)

    def get_help_panel(self, block_value, snapshot):
        attribute_type = block_value['attribute_type']
        value = str(snapshot.get_attribute_for_type(attribute_type))
        heading = f'{attribute_type} ({snapshot.report})'
        return HelpPanel(value, heading=heading)


@register_streamfield_block
class ActionImplementationPhaseReportFieldBlock(blocks.StaticBlock):
    class Meta:
        label = _("implementation phase")

    def get_report_export_column_label(self, value):
        return str(self.label)

    def get_report_export_value_for_action(self, block_value, action):
        if action.implementation_phase:
            return str(action.implementation_phase)
        return None

    def get_report_export_value_for_action_snapshot(self, block_value, snapshot):
        implementation_phase_id = snapshot.action_version.field_dict['implementation_phase_id']
        if implementation_phase_id:
            return str(ActionImplementationPhase.objects.get(id=implementation_phase_id))
        return None

    def add_xlsx_cell_format(self, block_value, workbook):
        return None

    def get_help_panel(self, block_value, snapshot):
        value = self.get_report_export_value_for_action_snapshot(block_value, snapshot) or ''
        heading = f'{self.label} ({snapshot.report})'
        return HelpPanel(value, heading=heading)


@register_streamfield_block
class ReportFieldBlock(blocks.StreamBlock):
    # All blocks mentioned here must implement get_report_export_column_label, get_report_export_value_for_action and
    # get_report_export_value_for_action_snapshot
    implementation_phase = ActionImplementationPhaseReportFieldBlock()
    attribute_type = ActionAttributeTypeReportFieldBlock()
    # TODO: action status

    graphql_types = [
        ActionImplementationPhaseReportFieldBlock, ActionAttributeTypeReportFieldBlock,
    ]
