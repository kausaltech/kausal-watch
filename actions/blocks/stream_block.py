from __future__ import annotations

import typing

from wagtail import blocks

from grapple.helpers import register_streamfield_block

from actions.action_fields import action_registry
from actions.blocks.mixins import ActionListPageBlockPresenceMixin
from actions.models.attributes import AttributeType
from actions.models.category import CategoryType

if typing.TYPE_CHECKING:
    from aplans.field_registry import BlockContext, ModelFieldRegistry

    from actions.models import Action


def generate_stream_block(
    name: str,
    fields: typing.Iterable[str | tuple[str, blocks.Block]],
    support_editing_from_other_form: bool = False,
    block_context: BlockContext = 'details',
    action_registry: ModelFieldRegistry[type[Action]] = action_registry,
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
        block = None
        if isinstance(field, tuple):
            field_name, block = field
            target_field_name = field_name
        else:
            field_name = field
            target_field_name = field_name
        if not block:
            block = action_registry.get_block(block_context, field_name)

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
