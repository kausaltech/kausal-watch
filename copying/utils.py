from __future__ import annotations

import re
import typing
from typing import Any

from django.contrib.contenttypes.fields import GenericForeignKey
from wagtail.blocks import StreamValue

from documents.models import AplansDocument
from images.models import AplansImage

if typing.TYPE_CHECKING:
    from collections.abc import Generator

    from django.db.models import Field, Model


def get_foreign_keys(instance: Model) -> Generator[Field]:
    """Get foreign keys for the given instance."""
    return (f for f in instance._meta.fields if f.many_to_one or f.one_to_one)


def get_generic_foreign_keys(instance: Model) -> Generator[GenericForeignKey]:
    """Get generic foreign keys for the given instance."""
    return (f for f in instance._meta.private_fields if isinstance(f, GenericForeignKey))


# https://stackoverflow.com/questions/2209159/disconnect-signals-for-models-and-reconnect-in-django
class temp_disconnect_signal:  # noqa: N801
    """Temporarily disconnect a model from a signal."""

    def __init__(self, signal, receiver, sender, dispatch_uid=None):
        self.signal = signal
        self.receiver = receiver
        self.sender = sender
        self.dispatch_uid = dispatch_uid

    def __enter__(self):
        self.signal.disconnect(
            receiver=self.receiver,
            sender=self.sender,
            dispatch_uid=self.dispatch_uid,
        )

    def __exit__(self, exc_type, exc_value, traceback):
        self.signal.connect(
            receiver=self.receiver,
            sender=self.sender,
            dispatch_uid=self.dispatch_uid,
            weak=False,
        )


def update_raw_data_element_at_content_path(
    raw_data: Any,  # noqa: ANN401
    content_path: list[str],
    new_value: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Update the value at a certain path in raw data from a streamfield."""
    if not content_path:
        return new_value
    path_element, *remaining_elements = content_path
    if isinstance(raw_data, list):
        for child in raw_data:
            # Depending on the type of the block, `path_element` can be either a UUID (for StreamBlock children) or
            # a block type name
            if child['id'] == path_element or child['type'] == path_element:
                child['value'] = update_raw_data_element_at_content_path(
                    child['value'],
                    remaining_elements,
                    new_value
                )
    elif isinstance(raw_data, dict):
        raw_data[path_element] = update_raw_data_element_at_content_path(
            raw_data[path_element],
            remaining_elements,
            new_value
        )
    else:
        raise TypeError(f"raw_data has unexpected type {type(raw_data)}")
    return raw_data


def update_streamfield_block(
    instance: Model,
    field_name: str,
    content_path: list[str],
    new_value: Any,  # noqa: ANN401
) -> None:
    """Update the value at a certain path in a given streamfield."""
    stream_value = getattr(instance, field_name)
    raw_data = list(stream_value.raw_data)
    update_raw_data_element_at_content_path(raw_data, content_path, new_value)
    stream_value.raw_data = raw_data
    # It's not enough to just change `raw_data`. We need to set the field itself too.
    # Comment from Wagtail's RawDataView:
    # once the BoundBlock representation has been accessed, any changes to fields within raw data will not
    # propagate back to the BoundBlock
    setattr(instance, field_name, StreamValue(stream_value.stream_block, stream_value.raw_data, is_lazy=True))


def update_rich_text_reference(
    instance: Model,
    field_name: str,
    old_referenced_object: Model,
    new_referenced_object: Model,
) -> None:
    """Update a reference to an image or document in a given rich text field."""
    assert type(old_referenced_object) is type(new_referenced_object)
    if isinstance(old_referenced_object, AplansDocument):
        pattern = r'<a\s+[^>]*linktype="document"[^>]*>'
    elif isinstance(old_referenced_object, AplansImage):
        pattern = r'<embed\s+[^>]*embedtype="image"[^>]*/>'
    else:
        raise TypeError(f"old_referenced_object has unexpected type {type(old_referenced_object)}")

    old_id = old_referenced_object.pk
    new_id = new_referenced_object.pk

    def replace_id_in_html_tag(match: re.Match) -> str:
        return re.sub(rf'\bid="{old_id}"', f'id="{new_id}"', match.group(0))

    old_value: str = getattr(instance, field_name)
    new_value = re.sub(pattern, replace_id_in_html_tag, old_value)
    assert new_value != old_value
    setattr(instance, field_name, new_value)
