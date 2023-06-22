import graphene
from django.apps import apps
from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLField, GraphQLForeignKey, GraphQLString
from grapple.registry import registry as grapple_registry
from typing import Any, List, Optional
from wagtail.admin.panels import HelpPanel
from wagtail import blocks

from actions.attributes import AttributeType
from actions.models import ActionImplementationPhase, AttributeType as AttributeTypeModel
from actions.blocks.choosers import ActionAttributeTypeChooserBlock
from aplans.graphql_types import register_graphene_node
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


class ReportValueInterface(graphene.Interface):
    field = graphene.NonNull(lambda: grapple_registry.streamfield_blocks.get(ReportFieldBlock))


@register_streamfield_block
class ActionAttributeTypeReportFieldBlock(blocks.StructBlock):
    attribute_type = ActionAttributeTypeChooserBlock(required=True, label=_("Field"))

    class Meta:
        label = _("Action field")

    graphql_fields = [
        GraphQLForeignKey('attribute_type', AttributeTypeModel, required=True)
    ]

    @register_graphene_node
    class Value(graphene.ObjectType):
        class Meta:
            name = 'ActionAttributeReportValue'
            interfaces = (ReportValueInterface,)

        attribute = graphene.Field('actions.schema.AttributeInterface')

    def value_for_action(self, block_value, action) -> Optional[Any]:
        wrapped_type = AttributeType.from_model_instance(block_value['attribute_type'])
        try:
            attribute = wrapped_type.get_attributes(action).get()
        except wrapped_type.ATTRIBUTE_MODEL.DoesNotExist:
            return None
        return attribute

    def value_for_action_snapshot(self, block_value, snapshot) -> Optional[Any]:
        return snapshot.get_attribute_for_type(block_value['attribute_type'])

    def graphql_value_for_action_snapshot(self, field, snapshot):
        attribute = self.value_for_action_snapshot(field.value, snapshot)
        if attribute is not None:
            # Change the ID of the attribute to include the snapshot, otherwise Apollo would cache the attribute value from
            # one point in time and use this for all other points in time of the same attribute
            attribute.id = f'{attribute.id}-snapshot-{snapshot.id}'
        return self.Value(
            field=field,
            attribute=attribute,
        )

    def xlsx_values_for_action(self, block_value, action) -> List[Any]:
        """Return the value for each of this attribute type's columns for the given action."""
        wrapped_type = AttributeType.from_model_instance(block_value['attribute_type'])
        attribute = self.value_for_action(block_value, action)
        return wrapped_type.xlsx_values(attribute)

    def xlsx_values_for_action_snapshot(self, block_value, snapshot) -> List[Any]:
        """Return the value for each of this attribute type's columns for the given snapshot."""
        wrapped_type = AttributeType.from_model_instance(block_value['attribute_type'])
        attribute = self.value_for_action_snapshot(block_value, snapshot)
        return wrapped_type.xlsx_values(attribute)

    def xlsx_column_labels(self, block_value) -> List[str]:
        """Return the label for each of this attribute type's columns."""
        wrapped_type = AttributeType.from_model_instance(block_value['attribute_type'])
        return wrapped_type.xlsx_column_labels()

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

    @register_graphene_node
    class Value(graphene.ObjectType):
        class Meta:
            name = 'ActionImplementationPhaseReportValue'
            interfaces = (ReportValueInterface,)

        implementation_phase = graphene.Field('actions.schema.ActionImplementationPhaseNode')

    def value_for_action(self, block_value, action) -> Optional[Any]:
        return action.implementation_phase

    def value_for_action_snapshot(self, block_value, snapshot) -> Optional[Any]:
        implementation_phase_id = snapshot.action_version.field_dict['implementation_phase_id']
        if implementation_phase_id:
            return ActionImplementationPhase.objects.get(id=implementation_phase_id)
        return None

    def graphql_value_for_action_snapshot(self, field, snapshot):
        return self.Value(
            field=field,
            implementation_phase=self.value_for_action_snapshot(field.value, snapshot),
        )

    def xlsx_values_for_action(self, block_value, action) -> List[Any]:
        value = self.value_for_action(block_value, action)
        return [str(value)]

    def xlsx_values_for_action_snapshot(self, block_value, snapshot) -> List[Any]:
        value = self.value_for_action_snapshot(block_value, snapshot)
        return [str(value)]

    def xlsx_column_labels(self, value) -> List[str]:
        return [str(self.label)]

    def add_xlsx_cell_format(self, block_value, workbook):
        return None

    def get_help_panel(self, block_value, snapshot):
        value = self.value_for_action_snapshot(block_value, snapshot) or ''
        heading = f'{self.label} ({snapshot.report})'
        return HelpPanel(str(value), heading=heading)


@register_streamfield_block
class ReportFieldBlock(blocks.StreamBlock):
    # All blocks mentioned here must implement xlsx_column_labels, value_for_action and value_for_action_snapshot
    implementation_phase = ActionImplementationPhaseReportFieldBlock()
    attribute_type = ActionAttributeTypeReportFieldBlock()
    # TODO: action status

    graphql_types = [
        ActionImplementationPhaseReportFieldBlock, ActionAttributeTypeReportFieldBlock,
    ]
