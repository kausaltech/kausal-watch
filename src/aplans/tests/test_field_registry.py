from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from wagtail import blocks

import pytest

from kausal_common.blocks import base as column_block_base
from kausal_common.blocks.registry import FieldBlockContext, FieldContextConfig, ModelFieldProperties, ModelFieldRegistry

from actions.blocks.base import ActionFilterBlock, ActionListContentBlock, ActionReportContentField
from actions.models import Action

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.django_db


@pytest.fixture
def field_name() -> Callable[[], str]:
    seq = 1

    def _field_name() -> str:
        return f'field-{seq}'

    return _field_name


@pytest.fixture
def model_field_properties_factory(field_name: Callable[[], str]) -> Callable[..., ModelFieldProperties]:
    def model_field_property(**kwargs: Any) -> ModelFieldProperties:
        if 'field_name' not in kwargs:
            kwargs['field_name'] = field_name()
        return ModelFieldProperties(**kwargs)

    return model_field_property


@pytest.fixture
def disabled_field_factory(model_field_properties_factory):
    def _disabled_field(block_context: FieldBlockContext) -> ModelFieldProperties:
        has = {
            'details': 'has_details_block',
            'dashboard': 'has_dashboard_column_block',
            'report': 'has_report_block',
            'list_filters': 'has_list_filters_block',
        }
        return model_field_properties_factory(
            **{has[block_context]: False},
        )

    return _disabled_field


@pytest.fixture
def field_registry():
    from actions.blocks.base import ActionContentBlockBase

    module = sys.modules[__name__]
    return ModelFieldRegistry(
        model=Action,
        target_module=module,
        contexts=[
            FieldContextConfig(
                context=FieldBlockContext.DETAILS,
                block_base_class=ActionContentBlockBase,
            ),
            FieldContextConfig(
                context=FieldBlockContext.REPORT,
                block_base_class=ActionContentBlockBase,
            ),
            FieldContextConfig(
                context=FieldBlockContext.LIST_FILTERS,
                block_base_class=ActionFilterBlock,
            ),
        ],
    )


@pytest.mark.parametrize('block_context', FieldBlockContext)
def test_disabled_fields_raise_for_blocks(block_context, disabled_field_factory, field_registry):
    disabled_field = disabled_field_factory(block_context)
    field_registry.register(
        disabled_field,
    )
    with pytest.raises(TypeError):
        field_registry.get_block(block_context, disabled_field.field_name)


@pytest.mark.parametrize('block_context', FieldBlockContext)
def test_defaults_have_all_blocks(field_registry, block_context: FieldBlockContext):
    field_name = 'status'
    field_registry.register(
        ModelFieldProperties(field_name=field_name),
    )
    block = field_registry.get_block(block_context, field_name)
    assert isinstance(block, blocks.Block)
    if block_context in ('details', 'report'):
        assert isinstance(block, ActionReportContentField)
        assert isinstance(block, ActionListContentBlock)
    if block_context == 'dashboard':
        assert isinstance(block, column_block_base.ColumnBlockBase)
