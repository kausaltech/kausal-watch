from __future__ import annotations

import importlib
import re
import typing
from dataclasses import dataclass
from typing import Any, Literal

from django.db.models import Model
from django.db.models.fields import Field
from django.db.models.fields.related import ForeignKey, ManyToManyField
from django.db.models.fields.reverse_related import ManyToOneRel

from loguru import logger

from aplans.utils import underscore_to_camelcase
from actions.blocks.column_block_base import ColumnBlockBase, DashboardColumnInterface
from .dynamic_blocks import generate_block_for_field


if typing.TYPE_CHECKING:
    from django.utils.functional import _StrPromise
    from wagtail import blocks

    from reports.report_formatters import ActionReportContentField, ReportFieldFormatter


type FieldType = Literal['Field', 'ManyToOneRel', 'ForeignKey', 'ManyToManyField', 'Custom']
type RegistryDict = dict[str, ModelFieldProperties]

@dataclass
class ModelFieldProperties:
    field_name: str
    field_type: FieldType | None = None
    model: type[Model] | None = None
    field_name_verbose: str | None = None  # TODO: strpromise too?
    custom_label: _StrPromise | None = None

    has_dashboard_column_block: bool = True
    has_details_block: bool = True
    has_report_block: bool = True

    dashboard_column_block_class: str | None = None
    details_block_class: str | None = None
    report_block_class: str | None = None
    report_formatter_class: str | None = None

    dashboard_column_block_class_name: str | None = None

    def __post_init__(self):
        if self.field_type is None and self.model is None:
            raise ValueError('Either field_type or model has to be set.')
        if self.field_type is None:
            self.field_type = self.get_field_type_for_field_name(self.field_name)

    @staticmethod
    def get_field_type(field) -> FieldType:
        if isinstance(field, ForeignKey):
            return 'ForeignKey'
        if isinstance(field, ManyToOneRel):
            return 'ManyToOneRel'
        if isinstance(field, ManyToManyField):
            return 'ManyToManyField'
        if isinstance(field, Field):
            return 'Field'
        msg = f'Unknown field type for {field}'
        raise TypeError(msg)

    def get_field_type_for_field_name(self, field_name: str) -> FieldType:
        if self.model is None:
            raise ValueError('Cannot get field type without model')
        field = self.model._meta.get_field(field_name)
        return ModelFieldProperties.get_field_type(field)

    @staticmethod
    def create_with_defaults(model, field) -> ModelFieldProperties:
        field_type = ModelFieldProperties.get_field_type(field)
        return ModelFieldProperties(
            field_type=field_type,
            field_name=field.name,
            field_name_verbose=getattr(field, 'verbose_name', None),
        )

    def get_report_block(self, field_name: str) -> ActionReportContentField:
        cls_ = self.get_report_block_class()
        block = cls_()
        return block

    def get_dashboard_column_block(self):
        pass

    def get_details_block(self):
        pass

    def get_report_block_class(self) -> type[ActionReportContentField] | None:
        if not self.has_report_block:
            return None
        if self.report_block_class:
            return self._import(self.report_block_class)
        return self._not_implemented()

    def get_report_formatter_class(self) -> type[ReportFieldFormatter] | None:
        if not self.has_report_block:
            return None
        if self.report_formatter_class:
            return self._import(self.report_formatter_class)
        return self._not_implemented()

    def get_dashboard_column_block_class(self) -> type[ColumnBlockBase] | None:
        if not self.has_dashboard_column_block:
            return None
        if self.dashboard_column_block_class:
            return self._import(self.dashboard_column_block_class)
        return self._not_implemented()

    def get_details_block_class(self) -> type[blocks.StructBlock] | None:
        if not self.has_details_block:
            return None
        if self.details_block_class:
            return self._import(self.details_block_class)
        return self._not_implemented()

    def _import[C](self, path: str) -> type[C]:
        names = re.match(r'^(.+)\.([^.]+)$', path)
        if not names:
            raise ValueError('Supply path.to.module.and.ClassName as a period-separated Python module path')
        module_name = names.group(1)
        class_name = names.group(2)
        module = importlib.import_module(module_name)
        try:
            return getattr(module, class_name)
        except AttributeError as e:
            msg = 'Class name {class_name} not found within module {module}'
            raise ValueError(msg) from e

    def _not_implemented(self):  # noqa: ANN202
        # Reminder to implement the default case
        return None
        #raise NotImplementedError('Implement default class generation!')


class ModelFieldRegistry[T: type[Model]]:
    """
    A field registry initialized upon app initialization.

    It stores metadata about what features model's fields supports and provides
    the implemetations for various blocks derived from the fields.

    Currently used for Action models.
    The features a field can support are:
    - Built-in-field customization such as visibility (plan-specific)  ??
    - Public site dashboard column blocks
    - Report spreadsheet column blocks
    - Block for the Action details page
    """

    model: T
    _registry: RegistryDict

    DISABLE = (
        'date_format',
        'decision_level',
        'dependency_role',
        'dependent_relationships',
        'id',
        'impact',
        'impact_groups',
        'merged_with',
        'monitoring_quality_points',
        'order',
        'plan',
        'schedule_continuous',
        'status_updates',
        'superseded_actions',
        'superseded_by',
        'uuid',
        'visibility',
    )

    DISABLE_DASHBOARD_COLUMN_BLOCKS = DISABLE + (
        # For these fields we do not want to generate blocks for the
        # action dashboard page
        'categories',
        'completion',
        'contact_persons',
        'dependencies',
        'description',
        'lead_paragraph',
        'links',
        'manual_status_reason',
        'merged_actions',
        'monitoring_quality_points',
        'official_name',
        'plan',  # TODO: wasn't this added?
        'related_actions',
        'related_indicators',
        'schedule',
    )
    # For these fields we do not want to generate blocks for the reports
    DISABLE_REPORT_BLOCKS = DISABLE_DASHBOARD_COLUMN_BLOCKS + (
        'indicators',
    )

    DISABLE_DETAILS_BLOCKS = DISABLE + (
        'completion',
        'end_date',
        'identifier',
        'implementation_phase',
        'indicators',
        'manual_status_reason',
        'name',
        'primary_org',
        'start_date',
        'status',
        'updated_at',
    )

    def __init__(self, model: T):
        self.model = model
        self._registry: RegistryDict = dict()

    def update_with_defaults(self) -> None:
        """Fill in missing fields with defaults, keeping already registered fields."""
        try:
            public_fields = self.model.public_fields  # type: ignore[attr-defined]
        except AttributeError as e:
            # TODO remove once static type checking is strict
            raise TypeError('Model must have public_fields specified in order to build field registry.') from e
        for field in self.model._meta.get_fields():
            name = field.name
            if name not in public_fields:
                continue
            if name in self._registry:
                continue
            props = ModelFieldProperties.create_with_defaults(self.model, field)
            if name in self.DISABLE_DASHBOARD_COLUMN_BLOCKS:
                props.has_dashboard_column_block = False
            if name in self.DISABLE_REPORT_BLOCKS:
                props.has_report_block = False
            if name in self.DISABLE_DETAILS_BLOCKS:
                props.has_details_block = False
            self._registry[name] = props

    def __getitem__(self, name: str) -> ModelFieldProperties:
        return self._registry[name]

    def register(self, props: ModelFieldProperties) -> None:
        self._registry[props.field_name] = props

    def register_all(self, *args) -> None:
        for x in args:
            self.register(x)
        self.update_with_defaults()

    def is_valid(self) -> bool:
        for key, props in self._registry.items():
            report_block = props.get_report_block_class()
            report_formatter = props.get_report_formatter_class()
            if report_block:
                if report_formatter:
                    report_block(report_value_formatter_class=report_formatter)
                else:
                    report_block()
            dashboard_column_block = props.get_dashboard_column_block_class()
            if dashboard_column_block:
                dashboard_column_block()
            details_block = props.get_details_block_class()
            if details_block:
                details_block()
            if props.has_dashboard_column_block and not props.has_report_block:
                logger.error(
                    f'Reporting block missing for field "{self.model.__name__}.{props.field_name}" with Dashboard column block',
                )
                return False
        return True

    def get_report_block(self, field_name: str) -> ActionReportContentField | None:
        props = self[field_name]
        if not props.has_report_block:
            return None
        cls_ = props.get_report_block_class()
        formatter_cls_ = props.get_report_formatter_class()
        params = {}
        if formatter_cls_:
            params['report_value_formatter_class'] = formatter_cls_
        if cls_ is None:
            cls_ = generate_block_for_field(self.model, field_name, params)
        block = cls_()
        return block

    def get_dashboard_column_block(self, field_name: str):
        props = self[field_name]
        if not props.has_dashboard_column_block:
            return None
        cls_ = props.get_dashboard_column_block_class()
        params = {}
        if props.custom_label:
            params['label'] = props.custom_label
        class_name = props.dashboard_column_block_class_name
        if class_name is None:
            class_name = f'{underscore_to_camelcase(field_name)}ColumnBlock'
        if cls_ is None:
            cls_ = generate_block_for_field(
                self.model,
                field_name,
                params,
                superclasses=(ColumnBlockBase,),
                class_name=class_name,
                graphql_interfaces=(DashboardColumnInterface,),
            )
        block = cls_()
        return block

    def get_details_block(self, field_name: str):
        props = self[field_name]
        if not props.has_details_block:
            return None
        cls_ = props.get_details_block_class()
        params = {}
        if props.custom_label:
            params['label'] = props.custom_label
        if cls_ is None:
            cls_ = generate_block_for_field(self.model, field_name, params)
        block = cls_()
        return block


def debug_registry(registry: ModelFieldRegistry):
    from rich.console import Console
    from rich.table import Table

    table = Table()
    table.add_column('Field name')
    table.add_column('Field type')
    table.add_column('Details page')
    table.add_column('Dashboard')
    table.add_column('Reporting')
    table.add_column('Custom formatter')

    def sort_key(p: ModelFieldProperties) -> tuple[Any, Any, Any, Any, Any]:
        return (
            -1 if p.has_details_block else 1,
            -1 if p.has_dashboard_column_block else 1,
            -1 if p.has_report_block else 1,
            p.field_type,
            p.field_name,
        )

    missing = set()
    not_implemented = '○'
    default_implementation = '●'
    custom_implementation = '❄'

    for props in sorted(
        registry._registry.values(),
        key=sort_key,
    ):
        dashboard = report = details = not_implemented
        formatter = ''
        if props.has_dashboard_column_block:
            dashboard = default_implementation
        if props.dashboard_column_block_class:
            dashboard = custom_implementation
        if props.has_report_block:
            report = default_implementation
        if props.report_block_class:
            report = custom_implementation
        if props.has_details_block:
            details = default_implementation
        if props.details_block_class:
            details = custom_implementation
        if props.report_formatter_class:
            formatter = custom_implementation

        if not all((x == not_implemented) for x in (dashboard, report, details)):
            table.add_row(
                props.field_name,
                props.field_type,
                details,
                dashboard,
                report,
                formatter,
            )
        else:
            missing.add(props.field_name)

    console = Console()
    console.print(table)
    console.print(f" Legend: yes {default_implementation}   no {not_implemented}   custom implementation {custom_implementation}")
    console.print("\n", "\n    ".join(['No block implementations for:'] + sorted(missing)))
