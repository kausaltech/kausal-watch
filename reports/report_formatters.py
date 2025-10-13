from __future__ import annotations

import typing
from abc import ABC, abstractmethod
from typing import Any

from django.apps import apps
from django.db.models.fields import Field
from django.utils.formats import date_format
from django.utils.translation import gettext, gettext_lazy as _, pgettext
from wagtail import blocks, fields

from grapple.models import GraphQLForeignKey

from aplans.utils import RestrictedVisibilityModel, convert_html_to_text

from actions.attributes import AttributeType
from actions.models.action import (
    Action,
    ActionCategoryThrough,
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
from actions.models.plan import Plan
from orgs.models import Organization
from reports.graphene_types import GrapheneValueClassProperties, generate_graphene_report_value_node_class
from reports.types import SerializedVersion
from reports.utils import (
    EXCEL_BUILTIN_NUMBER_FORMAT_FOR_DATES_WHICH_ADAPTS_TO_USER_LOCALE,
    EXCEL_BUILTIN_NUMBER_FORMAT_FOR_DATETIMES_WHICH_ADAPTS_TO_USER_LOCALE,
    get_attribute_for_type_from_related_objects,
    get_related_model_instances_for_action,
)

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    import graphene
    from django.db.models import Model
    from wagtail.blocks.base import BlockMeta  # pyright: ignore

    from actions.models import Plan
    from orgs.models import OrganizationQuerySet
    from reports.models import ActionSnapshot
    from reports.spreadsheets import ExcelReport
    from reports.types import AttributePath, SerializedAttributeVersion
    from reports.utils import ReportCellValue


type ValueType = Model | Iterable | str | None

class ReportFieldFormatter(ABC):
    block: ActionReportContentField
    ValueClass: type[graphene.ObjectType]

    def __init__(self, block: ActionReportContentField):
        self.block = block
        self.ValueClass = self.get_graphene_value_class()

    def value_for_action_snapshot(
            self,
            block_value: dict[str, ReportCellValue],
            snapshot: ActionSnapshot,
    ) -> ValueType:
        raise NotImplementedError

    @abstractmethod
    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str | int] | None:
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

    def value_for_action_snapshot(self, block_value, snapshot) -> ValueType:
        field_name = self.block.meta.field_name
        value = snapshot.action_version.field_dict[field_name]
        return value

    def extract_action_values(
            self,
            report: ExcelReport,
            block_value: dict,
            action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ) -> Sequence[ReportCellValue]:
        field_name = self.block.meta.field_name
        field = Action._meta.get_field(field_name)
        value = action.get(field_name)
        if isinstance(field, fields.RichTextField):
            value = convert_html_to_text(value)
        return [str(value) if value else '']

    def xlsx_column_labels(self, value: dict, plan: Plan | None = None) -> list[str]:
        field_name = self.block.meta.field_name
        field = Action._meta.get_field(field_name)
        if not isinstance(field, Field):
            raise TypeError('Do not use ActionSimpleFieldFormatter for relations')
        verbose_name = field.verbose_name
        return [str(verbose_name)]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str | int] | None:
        return None

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionSimpleFieldReportValue',
            value_field_name='value',
            value_field_type='graphene.String',
        )

class ActionDateFieldFormatter(ActionSimpleFieldFormatter):
    def extract_action_values(
            self,
            report: ExcelReport,
            block_value: dict,
            action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ) -> Sequence[ReportCellValue]:
        field_name = self.block.meta.field_name
        value = action.get(field_name)
        if value is None:
            return[None]
        return [value]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str | int] | None:
        # Do not use a string like "ddd-mmm" here, it will
        # not be localized properly
        return {
            'num_format':
            EXCEL_BUILTIN_NUMBER_FORMAT_FOR_DATES_WHICH_ADAPTS_TO_USER_LOCALE
        }

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionSimpleFieldReportValue',
            value_field_name='value',
            value_field_type='graphene.Date',
        )


class ActionDateTimeFieldFormatter(ActionSimpleFieldFormatter):
    def extract_action_values(
            self,
            report: ExcelReport,
            block_value: dict,
            action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ) -> Sequence[ReportCellValue]:
        field_name = self.block.meta.field_name
        value = action.get(field_name)
        if value is None:
            return[None]
        return [report.plan.to_local_timezone_as_naive(value)]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str | int] | None:
        # Do not use a string like "ddd-mmm" here, it will
        # not be localized properly
        return {
            'num_format':
            EXCEL_BUILTIN_NUMBER_FORMAT_FOR_DATETIMES_WHICH_ADAPTS_TO_USER_LOCALE
        }

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionSimpleFieldReportValue',
            value_field_name='value',
            value_field_type='graphene.DateTime',
        )


class ActionSingleRelatedModelFieldFormatter(ReportFieldFormatter):
    """A field referencing a single related model."""

    def value_for_action_snapshot(self, block_value, snapshot) -> ValueType:
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
        primary_key = action.get(f'{field_name}_id')
        related_model = field.related_model
        related_match  = get_related_model_instances_for_action(
            ('id', primary_key),
            related_objects,
            related_model,
        )
        assert len(related_match) < 2
        if not related_match:
            return [None]
        return [related_match[0].str]
        #str(related_objects[related_objects_key][str(primary_key)])]

    def xlsx_column_labels(self, value: dict, plan: Plan | None = None) -> list[str]:
        field_name = self.block.meta.field_name
        field = Action._meta.get_field(field_name)
        if not isinstance(field, Field):
            raise TypeError('Do not use ActionSimpleFieldFormatter for relations')
        verbose_name = field.verbose_name
        return [str(verbose_name)]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str | int] | None:
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
        return [verbose_name.capitalize() if verbose_name else field_name]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str | int] | None:
        return None

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionManyToOneFieldReportValue',
            value_field_name='value',
            value_field_type='graphene.String',
        )



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
            ('action_id', int(action['id'])),
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


class ActionIndicatorsFormatter(ActionManyToOneFieldFormatter):
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
        action_indicators = get_related_model_instances_for_action(
            ('action_id', int(action['id'])),
            related_objects,
            related_model,
        )
        indicators = get_related_model_instances_for_action(
            None,  # Match all indicators
            related_objects,
            apps.get_model('indicators', 'Indicator'),
        )
        indicator_goals = get_related_model_instances_for_action(
            None,  # Match all goals
            related_objects,
            apps.get_model('indicators', 'IndicatorGoal'),
        )
        available_organizations = report.plan_current_related_objects.organizations
        indicators_available_for_plan = {
            i.data['id']: i for i in indicators if (
                i.data['organization_id'] in available_organizations and
                i.data['visibility'] == RestrictedVisibilityModel.VisibilityState.PUBLIC
            )
        }
        indicators_for_this_action = [
            indicators_available_for_plan.get(ai.data['indicator_id']) for ai in action_indicators
        ]
        indicators_with_goals = [
            i for i in indicators_for_this_action if (
                i is not None and any(ig.data['indicator_id'] == i.data['id'] for ig in indicator_goals)
            )
        ]
        return [len(indicators_for_this_action), gettext('Yes') if len(indicators_with_goals) > 0 else gettext('No')]

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionTasksReportValue',
            value_field_name='tasks',
            value_field_type='graphene.String',
        )

    def xlsx_column_labels(self, value, plan: Plan | None = None) -> list[str]:
        return [gettext('Indicators'), gettext('Has goals')]


class ActionAttributeTypeReportFieldFormatter(ReportFieldFormatter):
    graphql_fields = [
        GraphQLForeignKey('attribute_type', AttributeTypeModel, required=True),
    ]

    def value_for_action_snapshot(self, block_value, snapshot) -> Model | None:
        return snapshot.get_attribute_for_type(block_value['attribute_type'])

    def graphql_value_for_action_snapshot(self, field, snapshot):
        attribute = self.value_for_action_snapshot(field.value, snapshot)
        if attribute is not None:
            # Change the ID of the attribute to include the snapshot, otherwise Apollo would cache the attribute value from
            # one point in time and use this for all other points in time of the same attribute
            attribute.pk = f'{attribute.pk}-snapshot-{snapshot.id}'
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

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str | int] | None:
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

        category_pks = self._get_category_ids(
            action['id'],
            related_objects.get('actions.models.action.ActionCategoryThrough', [])
        )
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

    def _get_category_ids(self, action_id: int, action_category_throughs: list[SerializedVersion]) -> list[int]:
        return [
            t.data['category_id'] for t in action_category_throughs
            if t.data['action_id'] == action_id
        ]

    def xlsx_column_labels(self, value, plan: Plan | None = None) -> list[str]:
        return [self.get_help_label(value)]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str | int] | None:
        return None

    def get_help_label(self, block_value):
        level = block_value.get('category_level')
        if level:
            return level.name
        return block_value.get('category_type').name

    def value_for_action_snapshot(self, block_value, snapshot) -> ValueType:
        category_type = block_value['category_type']
        related_objects = snapshot.get_related_versions()
        category_ids = self._get_category_ids(
            snapshot.action_version.field_dict.get('id'),
            [
                SerializedVersion.from_version(v) for v in related_objects
                if v.content_type.model_class() == ActionCategoryThrough
            ],
        )
        categories = Category.objects.filter(id__in=category_ids).filter(type=category_type)
        return categories

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionCategoryReportValue',
            value_field_name='category',
            value_field_type='actions.schema.CategoryNode',
        )


class ActionImplementationPhaseReportFieldFormatter(ReportFieldFormatter):
    def value_for_action_snapshot(self, block_value, snapshot) -> ValueType:
        implementation_phase_id = snapshot.action_version.field_dict['implementation_phase_id']
        if not implementation_phase_id:
            return '[%s]' % gettext('empty')
        try:
            implementation_phase = ActionImplementationPhase.objects.get(id=implementation_phase_id)
        except ActionImplementationPhase.DoesNotExist:
            return gettext('Unknown')
        if snapshot.action_version.field_dict.get('schedule_continuous') and implementation_phase.is_completed():
            return gettext('Continuous Action')
        return implementation_phase

    def extract_action_values(
            self, report: ExcelReport, block_value: dict, action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ) -> list[str | None]:

        pk = action.get('implementation_phase_id')
        if pk is None:
            return [None]
        implementation_phase = report.plan_current_related_objects.implementation_phases.get(int(pk))
        if not implementation_phase:
            result = '[%s]' % gettext('empty')
        elif action.get('schedule_continuous') and implementation_phase.is_completed():
            result = gettext('Continuous Action')
        else:
            result = str(implementation_phase)
        return [result]

    def xlsx_column_labels(self, value, plan: Plan | None = None) -> list[str]:
        return [str(self.block.label).capitalize()]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str | int] | None:
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

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str | int] | None:
        return None

    def value_for_action_snapshot(self, block_value, snapshot: ActionSnapshot) -> ValueType:
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
    def _find_organization_id(self, action_responsible_parties: Iterable[dict], action_id) -> int | None:
        try:
            return next(
                arp['organization_id'] for arp in action_responsible_parties
                if arp.get('action_id') == action_id and arp.get('role') == 'primary'
            )
        except StopIteration:
            return None

    def value_for_action_snapshot(self, block_value, snapshot) -> ValueType:
        related_versions = snapshot.get_related_versions()
        action_responsible_parties = (
            arp.field_dict
            for arp in related_versions if arp.content_type.model_class() == ActionResponsibleParty
        )
        org_id = self._find_organization_id(action_responsible_parties, snapshot.action_version.field_dict['id'])
        if org_id is None:
            return None
        try:
            return Organization.objects.get(pk=org_id)
        except Organization.DoesNotExist:
            return None

    def _get_organizations(
        self,
        action_responsible_parties: Iterable[dict],
        action_id: int,
        report: ExcelReport,
    ) -> dict[str, list[Organization]]:
        orgs_by_role: dict[str, list[Organization]] = {}
        for arp in action_responsible_parties:
            if arp.get('action_id') != action_id:
                continue
            role: str = arp.get('role') or 'other'
            org_id = arp['organization_id']
            org = report.plan_current_related_objects.organizations.get(org_id)
            if org is None:
                # The organization does not exist anymore in the plan
                continue
            orgs_by_role.setdefault(role, []).append(org)
        return orgs_by_role

    def extract_action_values(
            self, report: ExcelReport, block_value: dict, action: dict,
            related_objects: dict[str, list[SerializedVersion]],
            attribute_versions: dict[AttributePath, SerializedAttributeVersion],
            ):

        target_depth = block_value.get('target_ancestor_depth')
        organizations_by_role = self._get_organizations(
            (version.data for version in related_objects.get('actions.models.action.ActionResponsibleParty', [])),
            action['id'],
            report,
        )

        main_organization: Organization | None = None
        if 'primary' in organizations_by_role:
            main_organization = organizations_by_role['primary'][0]
        elif 'other' in organizations_by_role:
            main_organization = organizations_by_role['other'][0]
        elif 'collaborator' in organizations_by_role:
            main_organization = organizations_by_role['collaborator'][0]

        formatted_data = {}
        for role, orgs in organizations_by_role.items():
            formatted_data[role] = "; ".join([o.name for o in orgs])

        if target_depth is None:
            return [
                formatted_data.get('primary', ''),
                formatted_data.get('collaborator', ''),
                formatted_data.get('other', ''),
            ]
        if main_organization is None:
            parent_name = ''
        else:
            ancestors: OrganizationQuerySet = main_organization.get_ancestors()
            depth = len(ancestors)
            if depth == 0:
                parent = None
            elif depth == 1:
                parent = main_organization
            elif depth < target_depth:
                parent = ancestors[depth-1]
            else:
                parent = ancestors[target_depth-1]
            parent_name = parent.name if parent else ''
        return [
            formatted_data.get('primary', ''),
            formatted_data.get('collaborator', ''),
            formatted_data.get('other', ''),
            parent_name,
        ]

    def xlsx_column_labels(self, value: dict, plan: Plan | None = None) -> list[str]:
        labels = [
            gettext('Primary responsible party'),
            gettext('Collaborator'),
            gettext('Other responsible parties'),
        ]
        target_depth = value.get('target_ancestor_depth')
        if target_depth is None:
            return labels
        return labels + [pgettext('organization', 'Parent')]

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str | int] | None:
        return None

    def get_graphene_value_class_properties(self) -> GrapheneValueClassProperties:
        return GrapheneValueClassProperties(
            class_name='ActionResponsiblePartyReportValue',
            value_field_name='responsible_party',
            value_field_type='actions.schema.ActionResponsiblePartyNode',
        )


if typing.TYPE_CHECKING:
    class BlockMetaWithFieldName(BlockMeta):  # pyright: ignore
        field_name: str
else:
    class BlockMetaWithFieldName:
        pass


class ActionReportContentField(blocks.Block[BlockMetaWithFieldName]):  # pyright: ignore
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

    def value_for_action_snapshot(self, block_value, snapshot) -> ValueType:
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

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str | int] | None:
        return self.report_value_formatter.get_xlsx_cell_format(block_value)
