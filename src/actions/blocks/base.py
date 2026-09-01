from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

import graphene

from kausal_common.blocks.base import (
    ColumnBlockBase,
    ContentBlockBase,
    DashboardColumnInterface,
    FilterBlockBase,
    FilterBlockInterface,
    GeneralFieldBlockBase,
    GeneralFieldBlockInterface,
)
from kausal_common.blocks.fields import FieldBlockMetaInterface
from kausal_common.blocks.registry import FieldBlockContext

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from kausal_common.blocks.registry import ModelFieldRegistry

    from actions.models import Plan
    from actions.models.action import Action
    from reports.report_formatters import ReportFieldFormatter, ValueType
    from reports.spreadsheets import ExcelReport
    from reports.types import AttributePath, SerializedAttributeVersion, SerializedVersion
    from reports.utils import ReportCellValue


def get_action_registry() -> ModelFieldRegistry[Action]:
    from actions.action_fields import action_registry

    return action_registry


class ActionContentBlockInterface(GeneralFieldBlockInterface):
    source_field = graphene.Field(
        lambda: get_action_registry().get_field_enum_for_context(FieldBlockContext.DASHBOARD), required=False
    )


class ActionListContentBlock(ContentBlockBase):
    pass


if TYPE_CHECKING:
    from wagtail.blocks.base import BlockMeta

    class ReportBlockMeta(Protocol, BlockMeta):  # pyright: ignore
        field_name: str
        report_value_formatter_class: type[ReportFieldFormatter] | None

else:

    class ReportBlockMeta:
        pass


class ActionReportContentField[M: ReportBlockMeta = ReportBlockMeta](GeneralFieldBlockBase[M]):
    MUTABLE_META_ATTRIBUTES: ClassVar[Iterable[str]] = [
        *GeneralFieldBlockBase.MUTABLE_META_ATTRIBUTES,
        'report_value_formatter_class',
    ]
    graphql_interfaces = (FieldBlockMetaInterface, ActionContentBlockInterface)
    meta: M

    @cached_property
    def report_value_formatter(self) -> ReportFieldFormatter:
        return self.report_value_formatter_class(block=self)

    @property
    def report_value_formatter_class(self) -> type[ReportFieldFormatter]:
        from reports.report_formatters import ActionSimpleFieldFormatter

        if not hasattr(self.meta, 'report_value_formatter_class') or self.meta.report_value_formatter_class is None:
            return ActionSimpleFieldFormatter
        return self.meta.report_value_formatter_class

    def value_for_action_snapshot(self, block_value, snapshot) -> ValueType:
        return self.report_value_formatter.value_for_action_snapshot(block_value, snapshot)

    def graphql_value_for_action_snapshot(self, field, snapshot):
        return self.report_value_formatter.graphql_value_for_action_snapshot(field, snapshot)

    def extract_action_values(
        self,
        report: ExcelReport,
        block_value: dict[str, Any],
        action: dict[str, Any],
        related_objects: dict[str, list[SerializedVersion]],
        attribute_versions: dict[AttributePath, SerializedAttributeVersion],
    ) -> Sequence[ReportCellValue]:
        return self.report_value_formatter.extract_action_values(report, block_value, action, related_objects, attribute_versions)

    def xlsx_column_labels(self, value, plan: Plan | None = None) -> list[str]:
        try:
            ret = self.report_value_formatter.xlsx_column_labels(value, plan=plan)
        except Exception as e:
            print(f'{type(self)}: Error in xlsx_column_labels for {self.meta.field_name}: {e}')
            raise
        return ret

    def get_xlsx_cell_format(self, block_value: dict[str, Any]) -> dict[str, str | int] | None:
        return self.report_value_formatter.get_xlsx_cell_format(block_value)


class ActionContentBlockBase(ActionListContentBlock, ActionReportContentField[Any]):  # pyright: ignore[reportUnsafeMultipleInheritance]
    MUTABLE_META_ATTRIBUTES = {
        *ActionReportContentField.MUTABLE_META_ATTRIBUTES,
        *ActionListContentBlock.MUTABLE_META_ATTRIBUTES,
    }
    graphql_interfaces = (FieldBlockMetaInterface, ActionContentBlockInterface)
    graphql_fields = ActionListContentBlock.graphql_fields


class ActionColumnBlockInterface(DashboardColumnInterface):
    source_field = graphene.Field(
        lambda: get_action_registry().get_field_enum_for_context(FieldBlockContext.DASHBOARD), required=False
    )


class ActionColumnBlock(ColumnBlockBase):
    graphql_interfaces = (ActionColumnBlockInterface,)


class ActionFilterBlockInterface(FilterBlockInterface):
    source_field = graphene.Field(
        lambda: get_action_registry().get_field_enum_for_context(FieldBlockContext.LIST_FILTERS), required=False
    )


class ActionFilterBlock(FilterBlockBase):
    graphql_interfaces = (ActionFilterBlockInterface,)
