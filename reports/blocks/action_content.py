from abc import ABC, abstractmethod
from collections.abc import Iterable

import graphene
from django.db.models import Model
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext, gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLField, GraphQLForeignKey, GraphQLString
from grapple.registry import registry as grapple_registry
from typing import Any, List, Optional
from wagtail.admin.panels import HelpPanel
from wagtail import blocks

from actions.attributes import AttributeType
from actions.models import (
    ActionImplementationPhase,
    AttributeType as AttributeTypeModel,
    ActionResponsibleParty,
    CategoryLevel,
    CategoryType,
    ActionStatus,
    Category,
    Action
)
from orgs.models import Organization
from actions.blocks.choosers import ActionAttributeTypeChooserBlock, CategoryTypeChooserBlock, CategoryLevelChooserBlock
from aplans.graphql_types import register_graphene_node

from reports.blocks.choosers import ReportTypeChooserBlock, ReportTypeFieldChooserBlock
import typing
if typing.TYPE_CHECKING:
    from reports.spreadsheets import ExcelReport
    from reports.models import ActionSnapshot

from reports.utils import get_attribute_for_type_from_related_objects


@register_streamfield_block
class ReportComparisonBlock(blocks.StructBlock):
    report_type = ReportTypeChooserBlock(required=True)
    report_field = ReportTypeFieldChooserBlock(label=_('UUID of report field'), required=True)

    class Meta:
        label = _('Report comparison')

    def reports_to_compare(self, info, values):
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


class ReportFieldBlockInterface(ABC):
    @abstractmethod
    def value_for_action_snapshot(self, block_value, snapshot):
        return None

    @abstractmethod
    def get_help_panel(self, block_value, snapshot):
        return None


class FieldBlockWithHelpPanel(blocks.Block):
    def value_for_action_snapshot(self, block_value, snapshot):
        raise NotImplementedError(f'value_for_action_snapshot should be implemented for {self.__class__}')

    def get_help_label(self, value: Model):
        return None

    def get_help_panel(self, block_value, snapshot):
        value = self.value_for_action_snapshot(block_value, snapshot) or ''
        if not isinstance(value, Iterable) or isinstance(value, str):
            value = [value]
        value = "; ".join((str(v) for v in value))
        label = self.get_help_label(block_value)
        if label is None:
            label = self.label
        heading = f'{label} ({snapshot.report})'
        return HelpPanel(value, heading=heading)


ReportFieldBlockInterface.register(FieldBlockWithHelpPanel)


@register_streamfield_block
class ActionAttributeTypeReportFieldBlock(blocks.StructBlock, FieldBlockWithHelpPanel):
    attribute_type = ActionAttributeTypeChooserBlock(required=True)

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

    def extract_action_values(
            self,
            report: 'ExcelReport',
            block_value: dict,
            action: dict,
            related_objects: list[dict]) -> Optional[Any]:
        attribute_type_model_instance = block_value['attribute_type']
        wrapped_type = AttributeType.from_model_instance(attribute_type_model_instance)
        attribute_record = get_attribute_for_type_from_related_objects(
            report.plan_current_related_objects.action_content_type,
            int(action['id']),
            attribute_type_model_instance,
            related_objects
        )
        if attribute_record is None:
            return [None]
        return wrapped_type.xlsx_values(attribute_record, related_objects)

    def xlsx_column_labels(self, block_value) -> List[str]:
        """Return the label for each of this attribute type's columns."""
        wrapped_type = AttributeType.from_model_instance(block_value['attribute_type'])
        return wrapped_type.xlsx_column_labels()

    def get_xlsx_cell_format(self, block_value):
        wrapped_type = AttributeType.from_model_instance(block_value['attribute_type'])
        return wrapped_type.get_xlsx_cell_format()


@register_streamfield_block
class ActionCategoryReportFieldBlock(blocks.StructBlock, FieldBlockWithHelpPanel):
    category_type = CategoryTypeChooserBlock(required=True)
    category_level = CategoryLevelChooserBlock(required=False)

    class Meta:
        label = _("Action category")

    graphql_fields = [
        GraphQLForeignKey('category_type', CategoryType, required=True)
    ]

    @register_graphene_node
    class Value(graphene.ObjectType):
        class Meta:
            name = 'ActionCategoryReportValue'
            interfaces = (ReportValueInterface,)

        category = graphene.Field('actions.schema.CategoryNode')

    def extract_action_values(
        self, report: 'ExcelReport', block_value: dict, action: dict, related_objects: list[dict]
    ) -> Optional[Any]:
        category_type: CategoryType = block_value['category_type']

        def filter_by_type(categories: Iterable[Category | None]) -> Iterable[Category]:
            return [c for c in categories if c and c.type == category_type]
        def map_by_level(categories: Iterable[Category], level: CategoryLevel) -> Iterable[Category]:
            mappings = report.plan_current_related_objects.category_level_category_mappings.get(category_type.pk)
            if mappings is None:
                return categories
            return [mappings.get(level.pk, {}).get(c.pk) for c in categories]

        category_pks = action.get('categories', [])
        categories = filter_by_type([
            report.plan_current_related_objects.categories.get(int(pk)) for pk in category_pks
        ])

        level = block_value.get('category_level')
        if level is not None:
            categories = map_by_level(categories, level)

        category_names = "; ".join(c.name for c in categories if c)
        if len(category_names) == 0:
            return [None]
        return [category_names]

    def xlsx_column_labels(self, block_value) -> List[str]:
        return [self.get_help_label(block_value)]

    def get_xlsx_cell_format(self, block_value):
        return None

    def get_help_label(self, block_value):
        level = block_value.get('category_level')
        if level:
            return level.name
        return block_value.get('category_type').name

    def value_for_action_snapshot(self, block_value, snapshot):
        category_type = block_value['category_type']
        category_ids = snapshot.action_version.field_dict['categories']
        categories = Category.objects.filter(id__in=category_ids).filter(type=category_type)
        return categories


@register_streamfield_block
class ActionImplementationPhaseReportFieldBlock(blocks.StaticBlock, FieldBlockWithHelpPanel):
    class Meta:
        label = _("Implementation phase")

    @register_graphene_node
    class Value(graphene.ObjectType):
        class Meta:
            name = 'ActionImplementationPhaseReportValue'
            interfaces = (ReportValueInterface,)

        implementation_phase = graphene.Field('actions.schema.ActionImplementationPhaseNode')

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

    def extract_action_values(self, report: 'ExcelReport', block_value: dict, action: dict, related_objects: list[dict]) -> list[str]:
        pk = action.get('implementation_phase_id')
        if pk is None:
            return [None]
        return [str(report.plan_current_related_objects.implementation_phases.get(int(pk), f"[{_('empty')}]"))]

    def xlsx_column_labels(self, value) -> List[str]:
        return [str(self.label).capitalize()]

    def get_xlsx_cell_format(self, block_value):
        return None


@register_streamfield_block
class ActionStatusReportFieldBlock(blocks.StaticBlock, FieldBlockWithHelpPanel):
    class Meta:
        label = _("Status")

    @register_graphene_node
    class Value(graphene.ObjectType):
        class Meta:
            name = 'ActionStatusReportValue'
            interfaces = (ReportValueInterface,)

        implementation_phase = graphene.Field('actions.schema.ActionStatusNode')

    def extract_action_values(
            self,
            report: 'ExcelReport',
            block_value: dict,
            action: dict,
            related_objects: list[dict]
    ) -> list[str|None]:
        pk = action.get('status_id')
        if pk is None:
            return [None]
        return [str(report.plan_current_related_objects.statuses.get(int(pk)))]

    def xlsx_column_labels(self, value) -> List[str]:
        return [str(self.label).capitalize()]

    def get_xlsx_cell_format(self, block_value):
        return None

    def value_for_action_snapshot(self, block_value, snapshot: 'ActionSnapshot'):
        status_id = snapshot.action_version.field_dict['status_id']
        try:
            return ActionStatus.objects.get(pk=status_id)
        except ActionStatus.DoesNotExist:
            return None


@register_streamfield_block
class ActionResponsiblePartyReportFieldBlock(blocks.StructBlock, FieldBlockWithHelpPanel):
    target_ancestor_depth = blocks.IntegerBlock(
        label=_('Level of containing organization'),
        required=False,
        max_value=10,
        min_value=1,
        help_text=_(
            'In addition to the organization itself, an organizational unit containing the organization '
            'is included in the report. Counting from the top-level root organisation at level 1, which level '
            'in the organizational hierarchy should be used to find this containing organization? '
            'If left empty, don\'t add the containing organization to the report.'
        )
    )

    class Meta:
        label = _("Responsible party")

    @register_graphene_node
    class Value(graphene.ObjectType):
        class Meta:
            name = 'ActionResponsiblePartyReporteportValue'
            interfaces = (ReportValueInterface,)

        responsible_party = graphene.Field('actions.schema.ActionResponsiblePartyNode')

    def value_for_action_snapshot(self, block_value, snapshot):
        related_versions = snapshot.get_related_versions(
            ContentType.objects.get_for_model(Action))
        action_responsible_parties = (
            {'data': arp.field_dict}
            for arp in related_versions if arp.content_type.model_class() == ActionResponsibleParty
        )
        org_id = self._find_organization_id(action_responsible_parties, snapshot.action_version.field_dict['id'])
        try:
            return Organization.objects.get(pk=org_id)
        except Organization.DoesNotExist:
            return None

    def graphql_value_for_action_snapshot(self, field, snapshot):
        result = self.Value(
            field=field,
            responsible_party=self.value_for_action_snapshot(field.value, snapshot),
        )
        return result

    def _find_organization_id(self, action_responsible_parties, action_id):
        try:
            return next((
                arp['data']['organization_id'] for arp in action_responsible_parties
                if arp['data'].get('action_id') == action_id and (
                    arp['data'].get('role') == 'primary'
                )
            ))
        except StopIteration:
            return None

    def extract_action_values(
            self,
            report: 'ExcelReport',
            block_value: dict,
            action: dict,
            related_objects: list[dict]
    ) -> list[str | None]:
        organization_id = self._find_organization_id(
            related_objects['actions.models.action.ActionResponsibleParty'],
            action['id']
        )
        target_depth = block_value.get('target_ancestor_depth')
        value_length = 1
        if target_depth is not None:
            value_length += 1
        if organization_id is None:
            return [None] * value_length
        organization = report.plan_current_related_objects.organizations.get(organization_id)
        if organization is None:
            # The organization does not exist anymore in the plan
            return [None] * value_length
        if target_depth is None:
            return [organization.name]
        ancestors = organization.get_ancestors()
        depth = len(ancestors)
        if depth == 0:
            parent = None
        elif depth == 1:
            parent = organization
        elif depth < target_depth:
            parent = ancestors[depth-1]
        else:
            parent = ancestors[target_depth-1]
        parent_name = parent.name if parent else None
        return [organization.name, parent_name]

    def xlsx_column_labels(self, value: dict) -> List[str]:
        labels = [str(self.label).capitalize()]
        target_depth = value.get('target_ancestor_depth')
        if target_depth is None:
            return labels
        return labels + [gettext('Parent')]

    def get_xlsx_cell_format(self, block_value):
        return None


ReportFieldBlockInterface.register(ActionAttributeTypeReportFieldBlock)
ReportFieldBlockInterface.register(ActionCategoryReportFieldBlock)
ReportFieldBlockInterface.register(ActionImplementationPhaseReportFieldBlock)
ReportFieldBlockInterface.register(ActionStatusReportFieldBlock)
ReportFieldBlockInterface.register(ActionResponsiblePartyReportFieldBlock)


@register_streamfield_block
class ReportFieldBlock(blocks.StreamBlock):
    # All blocks mentioned here must implement xlsx_column_labels, value_for_action and value_for_action_snapshot
    implementation_phase = ActionImplementationPhaseReportFieldBlock()
    attribute_type = ActionAttributeTypeReportFieldBlock()
    responsible_party = ActionResponsiblePartyReportFieldBlock()
    category = ActionCategoryReportFieldBlock()
    status = ActionStatusReportFieldBlock()

    graphql_types = [
        ActionImplementationPhaseReportFieldBlock,
        ActionAttributeTypeReportFieldBlock,
        ActionResponsiblePartyReportFieldBlock,
        ActionCategoryReportFieldBlock,
        ActionStatusReportFieldBlock
    ]
