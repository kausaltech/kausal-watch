from __future__ import annotations

import importlib
import re
import typing
from dataclasses import dataclass
from typing import Any, Literal

from django.db.models import Model

from loguru import logger

from aplans.utils import underscore_to_camelcase

from actions.blocks.column_block_base import ColumnBlockBase, DashboardColumnInterface

from .dynamic_blocks import generate_block_for_field

if typing.TYPE_CHECKING:
    from django.utils.functional import _StrPromise
    from wagtail import blocks

    from reports.report_formatters import ReportFieldFormatter


def _import(path: str) -> type[Any]:
    """
    Import a class from a module based on a string.

    The string must be in the format path.to.package.ClassWithinPackage
    """
    names = re.match(r'^(.+)\.([^.]+)$', path)
    if not names:
        raise ValueError('Supply path.to.module.and.ClassName as a period-separated Python module path')
    module_name = names.group(1)
    class_name = names.group(2)
    module = importlib.import_module(module_name)
    try:
        return getattr(module, class_name)
    except AttributeError as e:
        msg = f'Class name {class_name} not found within module {module}'
        raise ValueError(msg) from e


type BlockContext = Literal['report', 'dashboard', 'details']
type FieldType = Literal['primitive', 'single', 'many', 'custom']
type RegistryDict = dict[str, ModelFieldProperties]

@dataclass
class BlockConfig:
    has_block: bool = True
    block_class: str | None = None

@dataclass
class ModelFieldProperties:
    field_name: str
    field_type: FieldType = 'primitive'
    custom_label: _StrPromise | None = None

    has_dashboard_column_block: bool = True
    has_details_block: bool = True
    has_report_block: bool = True

    dashboard_column_block_class: str | None = None
    details_block_class: str | None = None
    report_block_class: str | None = None

    report_formatter_class: str | None = None
    dashboard_column_block_class_name: str | None = None

    config: dict[BlockContext, BlockConfig] | None = None

    def __post_init__(self):
        self.config = dict(
            dashboard=BlockConfig(
                has_block=self.has_dashboard_column_block,
                block_class=self.dashboard_column_block_class,
            ),
            report=BlockConfig(
                has_block=self.has_report_block,
                block_class=self.report_block_class,
            ),
            details=BlockConfig(
                has_block=self.has_details_block,
                block_class=self.details_block_class,
            ),
        )
        if self.field_type is None:
            self.field_type = 'primitive'

    @staticmethod
    def create_with_defaults(model, name) -> ModelFieldProperties:
        return ModelFieldProperties(
            field_name=name,
        )

    def get_report_formatter_class(self) -> type[ReportFieldFormatter] | None:
        if not self.has_report_block:
            return None
        if self.report_formatter_class:
            return _import(self.report_formatter_class)
        return None

    def get_config(self, block_context: BlockContext) -> BlockConfig:
        if self.config is None or block_context not in self.config:
            raise ValueError('Improperly initialized.')
        return self.config[block_context]

    def get_block_class(self, block_context: BlockContext) -> type[blocks.Block] | None:
        cfg = self.get_config(block_context)
        if not cfg.has_block:
            return None
        if cfg.block_class:
            return _import(cfg.block_class)
        return None

    def get_block_class_kwargs(self, block_context: BlockContext) -> dict[str, Any]:
        result: dict[str, Any] = {'params': {}}
        if self.custom_label:
            result['params']['label'] = self.custom_label

        if block_context == 'dashboard':
            class_name = self.dashboard_column_block_class_name
            if class_name is None:
                class_name = f'{underscore_to_camelcase(self.field_name)}ColumnBlock'
            result['class_name'] = class_name
            result['superclasses'] = (ColumnBlockBase,)
            result['graphql_interfaces'] = (DashboardColumnInterface,)

        if block_context in ('report', 'details'):
            formatter_cls = self.get_report_formatter_class()
            if formatter_cls:
                result['params']['report_value_formatter_class'] = formatter_cls

        return result


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

    To be added:
    - Filter blocks
    """

    model: T
    _registry: RegistryDict
    disabled_fields: set[str]
    target_module: object
    _block_cache: dict[BlockContext, dict[str, type[blocks.Block]]]
    _common_block_class_cache: dict[str, type[blocks.Block]]

    def __init__(self, model: T, target_module: object):
        self.model = model
        self.target_module = target_module
        self._registry: RegistryDict = dict()
        self.disabled_fields = set()
        self._block_cache = dict()
        key: BlockContext
        for key in ('dashboard', 'report', 'details'):
            self._block_cache[key] = dict()
        self._common_block_class_cache = dict()

    def disable_fields(self, *fields: str) -> None:
        self.disabled_fields.update(fields)

    def update_with_defaults(self) -> None:
        """Fill in missing fields with defaults, keeping already registered fields."""
        try:
            public_fields = self.model.public_fields  # type: ignore[attr-defined]
        except AttributeError as e:
            # TODO remove once static type checking is strict
            raise TypeError('Model must have public_fields specified in order to build field registry.') from e
        for name in public_fields:
            if name in self._registry:
                continue
            props = ModelFieldProperties.create_with_defaults(self.model, name)
            if name in self.disabled_fields:
                props.has_dashboard_column_block = False
                props.has_report_block = False
                props.has_details_block = False
            self._registry[name] = props

    def __getitem__(self, name: str) -> ModelFieldProperties:
        return self._registry[name]

    def register(self, props: ModelFieldProperties) -> None:
        if props.field_name in self._registry:
            msg = f'Trying to register {props.field_name} twice'
            raise ValueError(msg)
        self._registry[props.field_name] = props

    def register_all(self, *args) -> None:
        for x in args:
            self.register(x)
        self.update_with_defaults()

    def get_block_class(self, block_context: BlockContext, field_name: str) -> type[blocks.Block]:
        cached = self._block_cache[block_context].get(field_name)
        if cached:
            return cached
        props = self[field_name]
        cfg = props.get_config(block_context)
        if not cfg.has_block:
            raise TypeError('No {block_context} block registered for {self.model}.{field_name}.')
        cls_ = props.get_block_class(block_context)
        if cls_ is not None:
            return cls_

        kwargs = props.get_block_class_kwargs(block_context)
        value = self._common_block_class_cache.get(field_name)
        if value is None:
            value = generate_block_for_field(
                self.model,
                field_name,
                target_module=self.target_module,
                **kwargs,
            )
            self._common_block_class_cache[field_name] = value
        self._block_cache[block_context][field_name] = value
        return value

    def get_block(self, block_context: BlockContext, field_name: str) -> blocks.Block:
        cls_ = self.get_block_class(block_context, field_name)
        return cls_()


def sort_key(p: ModelFieldProperties) -> tuple[Any, Any, Any, Any, Any]:
    return (
        -1 if p.has_details_block else 1,
        -1 if p.has_dashboard_column_block else 1,
        -1 if p.has_report_block else 1,
        p.field_type,
        p.field_name,
    )

NOT_IMPLEMENTED = '○'
DEFAULT_IMPLEMENTATION = '●'
CUSTOM_IMPLEMENTATION = '❄'

def debug_registry(registry: ModelFieldRegistry):
    from rich.console import Console
    from rich.table import Table

    table = Table(
        'Field name',
        'Field type',
        'Details page',
        'Dashboard',
        'Reporting',
        'Custom formatter',
    )

    missing = set()

    for props in sorted(
        registry._registry.values(),
        key=sort_key,
    ):
        dashboard = report = details = NOT_IMPLEMENTED
        formatter = ''
        if props.has_dashboard_column_block:
            dashboard = DEFAULT_IMPLEMENTATION
        if props.dashboard_column_block_class:
            dashboard = CUSTOM_IMPLEMENTATION
        if props.has_report_block:
            report = DEFAULT_IMPLEMENTATION
        if props.report_block_class:
            report = CUSTOM_IMPLEMENTATION
        if props.has_details_block:
            details = DEFAULT_IMPLEMENTATION
        if props.details_block_class:
            details = CUSTOM_IMPLEMENTATION
        if props.report_formatter_class:
            formatter = CUSTOM_IMPLEMENTATION

        if all((x == NOT_IMPLEMENTED) for x in (dashboard, report, details)):
            missing.add(props.field_name)
            continue

        table.add_row(
            props.field_name,
            props.field_type,
            details,
            dashboard,
            report,
            formatter,
        )


    console = Console()
    console.print(table)
    console.print(f"""
 {DEFAULT_IMPLEMENTATION} ───yes
 {NOT_IMPLEMENTED} ───no
 {CUSTOM_IMPLEMENTATION} ───custom implementation""")
    console.print("\n", "\n    ".join(['No block implementations for:'] + sorted(missing)))
