from __future__ import annotations

import typing
from typing import Any

from django.contrib.contenttypes.fields import GenericForeignKey
from wagtail.blocks import StreamValue

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
class temp_disconnect_signal:
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

    def __exit__(self, type, value, traceback):
        self.signal.connect(
            receiver=self.receiver,
            sender=self.sender,
            dispatch_uid=self.dispatch_uid,
            weak=False,
        )


def update_raw_data_element_at_content_path(raw_data: Any, content_path: list[str], new_value: Any) -> Any:
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
        raise AssertionError(f"raw_data has unexpected type {type(raw_data)}")
    return raw_data


def update_streamfield_block(instance: Model, field_name: str, content_path: list[str], new_value: Any) -> None:
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
