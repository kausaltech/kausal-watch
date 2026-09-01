from __future__ import annotations

import typing

from kausal_common.blocks.registry import FieldBlockContext
from kausal_common.blocks.stream_block import generate_stream_block as generate_stream_block_common

from actions.action_fields import action_registry
from actions.blocks.mixins import ActionListPageBlockPresenceMixin
from actions.models.attributes import AttributeType
from actions.models.category import CategoryType

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

    from wagtail import blocks

    from kausal_common.blocks.registry import ModelFieldRegistry

    from actions.models import Action


def generate_stream_block(
    name: str,
    fields: Iterable[str | tuple[str, blocks.Block[typing.Any]]],
    support_editing_from_other_form: bool = False,
    block_context: FieldBlockContext = FieldBlockContext.DETAILS,
    action_registry: ModelFieldRegistry[Action] = action_registry,
) -> type[blocks.StreamBlock]:
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

    return generate_stream_block_common(
        name,
        fields,
        block_context,
        field_registry=action_registry,
        mixins=mixins,
        extra_classvars=extra_args,
    )
