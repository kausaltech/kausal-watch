from __future__ import annotations

import typing

from wagtail import blocks

from grapple.helpers import register_streamfield_block

from actions.action_fields import action_registry
from actions.blocks.mixins import ActionListPageBlockPresenceMixin
from actions.models.attributes import AttributeType
from actions.models.category import CategoryType


def generate_stream_block(
    name: str,
    fields: typing.Iterable[str | tuple[str, blocks.Block] | tuple[str, str]],
    support_editing_from_other_form: bool = False,
    block_type: typing.Literal['details', 'dashboard'] = 'details',
):
    """
    Dynamically generates a stream block based on desired action fields.

    If an element in the fields iterable is a tuple, the first of the pair is the field name
    and the last of the pair is an already instantiated block that can be directly used.

    If an element is a string, the action field registry will be used to
    retrieve the correct block for that action field. (Those might be dynamically
    created classes or customized static classes.)

    If support_editing_from_other_form is True, add support to edit
    part of this block from a related model instance's edit form.
    Currently we support editing
      - an AttributeType's block from within the AttributeType's edit form and
      - a CategoryType's block from within the CategoryType's edit form.
    """
    mixins: tuple[type[typing.Any], ...] = tuple()
    extra_args = dict()

    if support_editing_from_other_form:
        mixins += (ActionListPageBlockPresenceMixin,)
        extra_args = {
            'model_instance_container_blocks': {
                AttributeType: 'attribute',
                CategoryType: 'categories',
            },
        }

    field_blocks = {}
    graphql_types = list()
    for field in fields:
        target_field_name = None
        if isinstance(field, tuple) and isinstance(field[1], blocks.Block):
            # Second element is a block instance already, use it directly
            field_name, block = field
            target_field_name = field_name
        else:
            if isinstance(field, tuple):
                # Second element is a string which should find
                # the standard block in the action field registry.
                # The key used in the block itself is different from this
                # and is saved to target_field_name
                field_name = field[1]
                target_field_name = field[0]
            else:
                field_name = field
                target_field_name = field_name
            if block_type == 'details':
                block = action_registry.get_details_block(field_name)
            else:
                assert block_type == 'dashboard'
                block = action_registry.get_dashboard_column_block(field_name)

        block_cls = type(block)
        if block_cls not in graphql_types:
            graphql_types.append(block_cls)
        field_blocks[target_field_name] = block

    block_class = type(name, (*mixins, blocks.StreamBlock), {
        '__module__': __name__,
        **field_blocks,
        **extra_args,
        'graphql_types': graphql_types,
    })

    register_streamfield_block(block_class)
    return block_class
