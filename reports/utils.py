from __future__ import annotations

import typing
from datetime import datetime

if typing.TYPE_CHECKING:
    from typing import Any, Literal

    from django.db.models import Model

    from .models import AttributePath, SerializedAttributeVersion, SerializedVersion

def get_attribute_for_type_from_related_objects(
        required_content_type_id: int,
        action_id: int,
        attribute_type_id: int,
        attribute_versions: dict[AttributePath, SerializedAttributeVersion],
) -> SerializedAttributeVersion | None:
    required_attribute_path: AttributePath = (
        required_content_type_id,
        action_id,
        attribute_type_id,
    )
    return attribute_versions.get(required_attribute_path)


def get_related_model_instances_for_action(
        # TODO: this is used in formatters -- see if it needs to be refactored
        action_id: int,
        related_objects: dict[str, list[SerializedVersion]],
        desired_model: type[Model] | Literal['self'] | Any | None,
):
    model_full_path = f"{desired_model.__module__}.{desired_model.__name__}"
    objects = related_objects.get(model_full_path)
    if objects is None:
        return []
    return [
        x for x in objects
        if action_id == int(x.data['action_id'])
    ]


def group_by_model(serialized_versions: list[SerializedVersion]) -> dict[str, list[SerializedVersion]]:
    result: dict[str, list[SerializedVersion]] = {}
    for version in serialized_versions:
        _cls = version.type
        key = f'{_cls.__module__}.{_cls.__name__}'
        result.setdefault(key, [])
        result[key].append(version)
    return result


type ReportCellValue = str | datetime | float | None
