from __future__ import annotations

import typing
from abc import ABC, abstractmethod
from typing import Any

from django.db.models.fields import Field
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _, pgettext
from wagtail import blocks, fields

from grapple.models import GraphQLForeignKey

from aplans.utils import convert_html_to_text

from actions.attributes import AttributeType
from actions.models.action import (
    Action,
    ActionImplementationPhase,
    ActionResponsibleParty,
    ActionStatus,
    ActionTask,
)
from actions.models.attributes import (
    AttributeType as AttributeTypeModel,
)
from actions.models.category import (
    Category,
    CategoryLevel,
    CategoryType,
)
from orgs.models import Organization
from reports.graphene_types import GrapheneValueClassProperties, generate_graphene_report_value_node_class
from reports.utils import get_attribute_for_type_from_related_objects, get_related_model_instances_for_action

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    import graphene

    from actions.models import Plan
    from reports.models import ActionSnapshot
    from reports.spreadsheets import ExcelReport
    from reports.utils import AttributePath, ReportCellValue, SerializedAttributeVersion, SerializedVersion


class ReportFieldFormatter(ABC):
    block: blocks.Block
    ValueClass: type[graphene.ObjectType]

    def __init__(self, block: blocks.Block):
        self.block = block
        self.ValueClass = self.get_graphene_value_class()

    def value_for_action_snapshot(
            self,
            block_value: dict[str, ReportCellValue],
            snapshot: ActionSnapshot,
    ) -> Any | None:
        raise NotImplementedError

    @abstractmethod
    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str] | None:
        pass

    def graphql_value_for_action_snapshot(self, field, snapshot):
        value_class_properties = self.get_graphene_value_class_properties()
        value_field_name = value_class_properties.value_field_name
        return self.ValueClass(
            field=field,
            **{value_field_name: self.value_for_action_snapshot(field.value, snapshot)},
        )

    @abstractmethod
    def extract_action_values(
            self, report: ExcelReport, block_value: dict, action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ) -> Sequence[ReportCellValue]:
        pass

    @abstractmethod
    def xlsx_column_labels(self, value, plan: Plan | None = None) -> list[str]:
        pass

    @abstractmethod
    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        pass

    def get_graphene_value_class(self) -> type[graphene.ObjectType]:
        properties = self.get_graphene_value_class_properties()
        return generate_graphene_report_value_node_class(properties)


class ActionSimpleFieldFormatter(ReportFieldFormatter):
    """A simple field is a field whose value is trivial to convert to a string with str."""

    def value_for_action_snapshot(self, block_value, snapshot) -> Any | None:
        value = snapshot.action_version.field_dict[block_value.get('field_name')]
        return value

    def extract_action_values(
            self,
            report: ExcelReport,
            block_value: dict,
            action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ):
        field_name = self.block.meta.field_name
        field = Action._meta.get_field(field_name)
        value = action.get(field_name)
        if isinstance(field, fields.RichTextField):
            value = convert_html_to_text(value)
        return [str(value)]

    def xlsx_column_labels(self, value: dict, plan: Plan | None = None) -> list[str]:
        field_name = self.block.meta.field_name
        field = Action._meta.get_field(field_name)
        if not isinstance(field, Field):
            raise TypeError('Do not use ActionSimpleFieldFormatter for relations')
        verbose_name = field.verbose_name
        return [str(verbose_name)]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str] | None:
        return None

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionSimpleFieldReportValue',
            value_field_name='value',
            value_field_type='graphene.String',
        )

class ActionManyToOneFieldFormatter(ReportFieldFormatter):
    """Formats the many values related to one action by concatenating them so they can be output into one spreadsheet cell."""

    def extract_action_values(
            self, report: ExcelReport, block_value: dict, action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ):
        field_name = self.block.meta.field_name
        field = Action._meta.get_field(field_name)
        value = block_value
        if isinstance(field, fields.RichTextField):
            value = convert_html_to_text(value)
        return [str(value)]

    def xlsx_column_labels(self, value, plan: Plan | None = None) -> list[str]:
        field_name = self.block.meta.field_name
        field = Action._meta.get_field(field_name)
        verbose_name = field.related_model._meta.verbose_name_plural
        return [verbose_name.capitalize()]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str] | None:
        return None


class ActionTasksFormatter(ActionManyToOneFieldFormatter):
    def extract_action_values(
            self, report: ExcelReport,
            block_value: dict,
            action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
    ):
        field_name = self.block.meta.field_name
        field = Action._meta.get_field(field_name)
        related_model = field.related_model
        tasks = get_related_model_instances_for_action(
            int(action['id']),
            related_objects,
            related_model,
        )
        formatted = []
        for t in tasks:
            data = t.data
            state = next(str(s[1]) for s in ActionTask.STATES if s[0] == data['state'])
            if data['state'] == ActionTask.COMPLETED:
                completed_at_date = data["completed_at"]
                state += f' {date_format(completed_at_date)}'
            else:
                due_date = data['due_at']
                state += f", {_('due date')}: {date_format(due_date)}"
            formatted.append(
                f"• {data['name']} [{state}]",
            )
        return ["\n".join(formatted)]

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionTasksReportValue',
            value_field_name='tasks',
            value_field_type='graphene.String',
        )

    def xlsx_column_labels(self, value, plan: Plan | None = None) -> list[str]:
        if plan is None:
            return super().xlsx_column_labels(value)
        return [str(plan.general_content.get_action_task_term_display_plural())]


class ActionAttributeTypeReportFieldFormatter(ReportFieldFormatter):
    graphql_fields = [
        GraphQLForeignKey('attribute_type', AttributeTypeModel, required=True),
    ]

    def value_for_action_snapshot(self, block_value, snapshot) -> Any | None:
        return snapshot.get_attribute_for_type(block_value['attribute_type'])

    def graphql_value_for_action_snapshot(self, field, snapshot):
        attribute = self.value_for_action_snapshot(field.value, snapshot)
        if attribute is not None:
            # Change the ID of the attribute to include the snapshot, otherwise Apollo would cache the attribute value from
            # one point in time and use this for all other points in time of the same attribute
            attribute.id = f'{attribute.id}-snapshot-{snapshot.id}'
        return self.get_graphene_value_class()(
            field=field,
            attribute=attribute,
        )

    def extract_action_values(
            self, report: ExcelReport, block_value: dict, action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ):
        attribute_type_model_instance = block_value['attribute_type']
        wrapped_type: AttributeType = AttributeType.from_model_instance(attribute_type_model_instance)
        attribute_record = get_attribute_for_type_from_related_objects(
            report.plan_current_related_objects.action_content_type.id,
            int(action['id']),
            attribute_type_model_instance.pk,
            attribute_versions,
        )
        if attribute_record is None:
            labels = self.xlsx_column_labels(block_value)
            return [None] * len(labels)
        return wrapped_type.xlsx_values(attribute_record, related_objects)

    def xlsx_column_labels(self, value, plan: Plan | None = None) -> list[str]:
        """Return the label for each of this attribute type's columns."""
        wrapped_type: AttributeType = AttributeType.from_model_instance(value['attribute_type'])
        return wrapped_type.xlsx_column_labels(plan=plan)

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str] | None:
        wrapped_type: AttributeType = AttributeType.from_model_instance(block_value['attribute_type'])
        return wrapped_type.get_xlsx_cell_format()

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionAttributeReportValue',
            value_field_name='attribute',
            value_field_type='actions.schema.AttributeInterface',
        )


class ActionCategoryReportFieldFormatter(ReportFieldFormatter):
    graphql_fields = [
        GraphQLForeignKey('category_type', CategoryType, required=True),
    ]

    def extract_action_values(
            self, report: ExcelReport, block_value: dict, action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ):

        category_type: CategoryType = block_value['category_type']

        def filter_by_type(categories: Iterable[Category | None]) -> Iterable[Category]:
            return [c for c in categories if c and c.type == category_type]

        def map_by_level(categories: Iterable[Category], level: CategoryLevel) -> Iterable[Category | None]:
            mappings = report.plan_current_related_objects.category_level_category_mappings.get(category_type.pk)
            if mappings is None:
                return categories
            return [mappings.get(level.pk, {}).get(c.pk) for c in categories]

        category_pks = action.get('categories', [])
        categories: Iterable[Category] = filter_by_type([
            report.plan_current_related_objects.categories.get(int(pk)) for pk in category_pks
        ])

        level = block_value.get('category_level')
        mapped_categories: Iterable[Category | None] = categories
        if level is not None:
            mapped_categories = map_by_level(categories, level)

        category_names = "; ".join(c.name for c in mapped_categories if c)
        if len(category_names) == 0:
            return [None]
        return [category_names]

    def xlsx_column_labels(self, value, plan: Plan | None = None) -> list[str]:
        return [self.get_help_label(value)]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str] | None:
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

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionCategoryReportValue',
            value_field_name='category',
            value_field_type='actions.schema.CategoryNode',
        )


class ActionImplementationPhaseReportFieldFormatter(ReportFieldFormatter):
    def value_for_action_snapshot(self, block_value, snapshot) -> Any | None:
        implementation_phase_id = snapshot.action_version.field_dict['implementation_phase_id']
        if implementation_phase_id:
            return ActionImplementationPhase.objects.get(id=implementation_phase_id)
        return None

    def extract_action_values(
            self, report: ExcelReport, block_value: dict, action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ) -> list[str | None]:

        pk = action.get('implementation_phase_id')
        if pk is None:
            return [None]
        return [str(report.plan_current_related_objects.implementation_phases.get(int(pk), f"[{_('empty')}]"))]

    def xlsx_column_labels(self, value, plan: Plan | None = None) -> list[str]:
        return [str(self.block.label).capitalize()]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str] | None:
        return None

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionImplementationPhaseReportValue',
            value_field_name='implementation_phase',
            value_field_type='actions.schema.ActionImplementationPhaseNode',
        )


class ActionStatusReportFieldFormatter(ReportFieldFormatter):
    def extract_action_values(
            self, report: ExcelReport, block_value: dict, action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ):

        pk = action.get('status_id')
        if pk is None:
            return [None]
        return [str(report.plan_current_related_objects.statuses.get(int(pk)))]

    def xlsx_column_labels(self, value, plan: Plan | None = None) -> list[str]:
        return [str(self.block.label).capitalize()]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str] | None:
        return None

    def value_for_action_snapshot(self, block_value, snapshot: ActionSnapshot):
        status_id = snapshot.action_version.field_dict['status_id']
        try:
            return ActionStatus.objects.get(pk=status_id)
        except ActionStatus.DoesNotExist:
            return None

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionStatusReportValue',
            value_field_name='status',
            value_field_type='actions.schema.ActionStatusNode',
        )


class ActionResponsiblePartyReportFieldFormatter(ReportFieldFormatter):
    def value_for_action_snapshot(self, block_value, snapshot):
        related_versions = snapshot.get_related_versions()
        action_responsible_parties = (
            arp.field_dict
            for arp in related_versions if arp.content_type.model_class() == ActionResponsibleParty
        )
        org_id = self._find_organization_id(action_responsible_parties, snapshot.action_version.field_dict['id'])
        try:
            return Organization.objects.get(pk=org_id)
        except Organization.DoesNotExist:
            return None

    def _find_organization_id(self, action_responsible_parties: Iterable[dict], action_id) -> int | None:
        try:
            return next(
                arp['organization_id'] for arp in action_responsible_parties
                if arp.get('action_id') == action_id and arp.get('role') == 'primary'
            )
        except StopIteration:
            return None

    def extract_action_values(
            self, report: ExcelReport, block_value: dict, action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ):
        organization_id = self._find_organization_id(
            (version.data for version in related_objects['actions.models.action.ActionResponsibleParty']),
            action['id'],
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

    def xlsx_column_labels(self, value: dict, plan: Plan | None = None) -> list[str]:
        labels = [str(self.block.label)]
        target_depth = value.get('target_ancestor_depth')
        if target_depth is None:
            return labels
        return labels + [pgettext('organization', 'Parent')]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str] | None:
        return None

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionResponsiblePartyReportValue',
            value_field_name='responsible_party',
            value_field_type='actions.schema.ActionResponsiblePartyNode',
        )


class ActionReportContentField(blocks.Block):
    report_value_formatter: ReportFieldFormatter
    report_value_formatter_class: type[ReportFieldFormatter]

    def __init__(self, *args, report_value_formatter_class: type[ReportFieldFormatter] | None = None, **kwargs):
        report_value_formatter_class = self.get_report_value_formatter_class()
        self.report_value_formatter = report_value_formatter_class(self)
        super().__init__(*args, **kwargs)

    def get_report_value_formatter_class(self) -> type[ReportFieldFormatter]:
        if not hasattr(self, 'report_value_formatter_class') or self.report_value_formatter_class is None:
            return ActionSimpleFieldFormatter
        return self.report_value_formatter_class

    def value_for_action_snapshot(self, block_value, snapshot) -> Any | None:
        return self.report_value_formatter.value_for_action_snapshot(block_value, snapshot)

    def graphql_value_for_action_snapshot(self, field, snapshot):
        return self.report_value_formatter.graphql_value_for_action_snapshot(field, snapshot)

    def extract_action_values(
            self, report: ExcelReport, block_value: dict, action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ) -> Sequence[ReportCellValue]:
        return self.report_value_formatter.extract_action_values(report, block_value, action, related_objects, attribute_versions)

    def xlsx_column_labels(self, value, plan: Plan | None = None) -> list[str]:
        return self.report_value_formatter.xlsx_column_labels(value, plan=plan)

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str] | None:
        return self.report_value_formatter.get_xlsx_cell_format(block_value)
