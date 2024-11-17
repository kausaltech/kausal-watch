from __future__ import annotations

import sys

from django.db.models.fields import Field
from django.db.models.fields.related import ForeignKey, ManyToManyField
from django.db.models.fields.reverse_related import ManyToOneRel
from wagtail import blocks

import pytest

from aplans.field_registry import ALL_CONTEXTS, ModelFieldProperties, ModelFieldRegistry, BlockContext
from aplans import dynamic_blocks
from actions.blocks import column_block_base
from reports import report_formatters

from actions.models import Action



pytestmark = pytest.mark.django_db


@pytest.fixture()
def field_name():
    seq = 1
    def _field_name():
        return f'field-{seq!s}'
    return _field_name

@pytest.fixture()
def model_field_properties_factory(field_name):
    def model_field_property(**kwargs):
        if 'field_name' not in kwargs:
            kwargs['field_name'] = field_name()
        return ModelFieldProperties(**kwargs)
    return model_field_property


@pytest.fixture()
def disabled_field_factory(model_field_properties_factory):
    def _disabled_field(block_context):
         has = {
             'details': 'has_details_block',
             'dashboard': 'has_dashboard_column_block',
             'report': 'has_report_block',
         }
         return model_field_properties_factory(
             **{has[block_context]: False},
         )
    return _disabled_field


@pytest.fixture()
def field_registry():
    module = sys.modules[__name__]
    return ModelFieldRegistry(model=Action, target_module=module)


@pytest.mark.parametrize('block_context', ALL_CONTEXTS)
def test_disabled_fields_raise_for_blocks(block_context, disabled_field_factory, field_registry):
    disabled_field = disabled_field_factory(block_context)
    field_registry.register(
        disabled_field,
    )
    with pytest.raises(TypeError):
        field_registry.get_block(block_context, disabled_field.field_name)


@pytest.mark.parametrize('block_context', ALL_CONTEXTS)
def test_defaults_have_all_blocks(field_registry, block_context: BlockContext):
    field_name = 'status'
    field_registry.register(
        ModelFieldProperties(field_name=field_name),
    )
    block = field_registry.get_block(block_context, field_name)
    assert isinstance(block, blocks.Block)
    if block_context in ('details', 'report'):
        assert isinstance(block, report_formatters.ActionReportContentField)
        assert isinstance(block, dynamic_blocks.ActionListContentBlock)
    if block_context == 'dashboard':
        assert isinstance(block, column_block_base.ColumnBlockBase)
