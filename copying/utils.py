from __future__ import annotations

import re
import typing
from typing import Any

from django.contrib.contenttypes.fields import GenericForeignKey
from wagtail.blocks import StreamValue

from documents.models import AplansDocument
from images.models import AplansImage
from indicators.models import Indicator

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


def update_reference_in_raw_data(
    raw_data: Any,  # noqa: ANN401
    content_path: list[str],
    old_object: Model,
    new_object: Model,
) -> Any:  # noqa: ANN401
    """
    Update a reference at a certain path in raw data from a streamfield.

    Also see documentation of `update_streamfield_block()`.
    """
    if not content_path:
        if raw_data in (old_object.pk, new_object.pk):  # perhaps it was updated already
            return new_object.pk
        assert isinstance(raw_data, str)
        # Guess it's a rich-text HTML string
        return update_reference_in_html(raw_data, old_object, new_object)
    path_element, *remaining_elements = content_path
    if isinstance(raw_data, list):
        for child in raw_data:
            # Depending on the type of the block, `path_element` can be either a UUID (for StreamBlock children) or
            # a block type name
            if child['id'] == path_element or child['type'] == path_element:
                child['value'] = update_reference_in_raw_data(
                    child['value'],
                    remaining_elements,
                    old_object,
                    new_object,
                )
    elif isinstance(raw_data, dict):
        raw_data[path_element] = update_reference_in_raw_data(
            raw_data[path_element],
            remaining_elements,
                    old_object,
                    new_object,
        )
    else:
        raise TypeError(f"raw_data has unexpected type {type(raw_data)}")
    return raw_data


def update_streamfield_block(
    instance: Model,
    field_name: str,
    content_path: list[str],
    old_object: Model,
    new_object: Model,
) -> None:
    """
    Update a reference to an object at a certain path in a given streamfield.

    Note that the content path may not be very precise. Indeed, the value pointed to by the content path might be
    something that may still contain other things than just a pure reference; for example, the content path could point
    to a rich-text block, which may contain an HTML string with all kinds of things besides the reference we're looking
    for. In other cases, the situation is simpler, as often the value pointed to by the content path is simply a PK. But
    in general, updating the reference is not as easy as just replacing whatever we find at the content path. This code
    tries to do the right thing.
    """
    stream_value = getattr(instance, field_name)
    raw_data = list(stream_value.raw_data)
    update_reference_in_raw_data(raw_data, content_path, old_object, new_object)
    stream_value.raw_data = raw_data
    # It's not enough to just change `raw_data`. We need to set the field itself too.
    # Comment from Wagtail's RawDataView:
    # once the BoundBlock representation has been accessed, any changes to fields within raw data will not
    # propagate back to the BoundBlock
    setattr(instance, field_name, StreamValue(stream_value.stream_block, stream_value.raw_data, is_lazy=True))


def update_reference_in_html(
    html: str,
    old_referenced_object: Model,
    new_referenced_object: Model,
) -> str:
    """Update a reference to an image, document, or indicator in a given HTML string."""
    assert type(old_referenced_object) is type(new_referenced_object)
    if isinstance(old_referenced_object, AplansDocument):
        pattern = r'<a\s+[^>]*linktype="document"[^>]*>'
    elif isinstance(old_referenced_object, AplansImage):
        pattern = r'<embed\s+[^>]*embedtype="image"[^>]*/>'
    elif isinstance(old_referenced_object, Indicator):
        pattern = r'<a\s+[^>]*linktype="indicator"[^>]*>'
    else:
        raise TypeError(f"old_referenced_object has unexpected type {type(old_referenced_object)}")

    old_id = old_referenced_object.pk
    new_id = new_referenced_object.pk

    def replace_reference_in_html_tag(match: re.Match) -> str:
        tag = match.group(0)
        # Replace the id attribute
        tag = re.sub(rf'\bid="{old_id}"', f'id="{new_id}"', tag)
        # For indicators, also replace the uuid attribute
        if isinstance(old_referenced_object, Indicator):
            assert isinstance(new_referenced_object, Indicator)
            old_uuid = str(old_referenced_object.uuid)
            new_uuid = str(new_referenced_object.uuid)
            tag = re.sub(rf'\buuid="{old_uuid}"', f'uuid="{new_uuid}"', tag)
        return tag

    new_html = re.sub(pattern, replace_reference_in_html_tag, html)

    if new_html != html:
        return new_html

    # If nothing changed, make some sanity checks
    if f'id="{new_id}"' not in html:
        raise ValueError(
            f"Failed to update reference from {old_id} to {new_id} in HTML: "
            f"old reference not found and new reference not present"
        )

    # For indicators, also verify that the UUID was updated
    if isinstance(old_referenced_object, Indicator):
        assert isinstance(new_referenced_object, Indicator)
        new_uuid = str(new_referenced_object.uuid)
        if f'uuid="{new_uuid}"' not in html:
            raise ValueError(f"Reference ID was updated but UUID was not for indicator {new_id}")

    # Reference was already updated -- return unchanged HTML.
    # This can happen as the reference index may contain, e.g., `description`, `description_en` and `description_i18n`,
    # which may point to the same field.
    return html


def update_rich_text_reference_in_field(
    instance: Model,
    field_name: str,
    old_referenced_object: Model,
    new_referenced_object: Model,
) -> None:
    """Update a reference to an image, document, or indicator in a given rich text field."""
    old_value: str = getattr(instance, field_name)
    new_value = update_reference_in_html(old_value, old_referenced_object, new_referenced_object)
    setattr(instance, field_name, new_value)
