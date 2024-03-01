from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import TypedDict
from django.contrib.contenttypes.models import ContentType
from modelcluster.fields import ParentalManyToManyDescriptor
from reversion.models import Version

from actions.models.attributes import Attribute

AttributePath = tuple[int, int, int]


@dataclass
class SerializedVersion:
    type: type
    data: dict
    str: str


@dataclass
class SerializedAttributeVersion(SerializedVersion):
    attribute_path: AttributePath


def make_attribute_path(version_data) -> AttributePath:
    return (
        version_data['content_type_id'],
        version_data['object_id'],
        version_data['type_id']
    )


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


def prepare_serialized_model_version(version: Version) -> SerializedVersion:
    serialized = SerializedVersion(
        type=version.content_type.model_class(),
        data=version.field_dict,
        str=version.object_repr,
    )
    if issubclass(serialized.type, Attribute):
        return SerializedAttributeVersion(
            **asdict(serialized),
            attribute_path=make_attribute_path(version.field_dict),
        )
    return serialized


def group_by_model(serialized_versions: list[SerializedVersion]) -> dict[str, list[SerializedVersion]]:
    result = {}
    for version in serialized_versions:
        _cls = version.type
        key = f'{_cls.__module__}.{_cls.__name__}'
        result.setdefault(key, [])
        result[key].append(version)
    return result
