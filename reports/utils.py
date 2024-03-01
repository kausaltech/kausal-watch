from __future__ import annotations
import typing

if typing.TYPE_CHECKING:
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
        attribute_type_id
    )
    return attribute_versions.get(required_attribute_path)


def group_by_model(serialized_versions: list[SerializedVersion]) -> dict[str, list[SerializedVersion]]:
    result = {}
    for version in serialized_versions:
        _cls = version.type
        key = f'{_cls.__module__}.{_cls.__name__}'
        result.setdefault(key, [])
        result[key].append(version)
    return result
