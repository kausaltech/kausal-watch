from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import TypedDict
from django.contrib.contenttypes.models import ContentType
from modelcluster.fields import ParentalManyToManyDescriptor
from reversion.models import Version

from actions.models.attributes import AttributeTypeChoiceOption
from actions.models.attributes import Attribute


@dataclass
class SerializedVersion:
    type: type
    data: dict
    str: str


@dataclass
class SerializedAttributeVersion(SerializedVersion):
    attribute_path: str


def make_attribute_path(version_data):
    return (
        version_data['content_type_id'],
        version_data['object_id'],
        version_data['type_id']
    )


def get_attribute_for_type_from_related_objects(
        required_content_type: ContentType,
        action_id: int,
        attribute_type,
        versions_by_model: dict[str, list[SerializedVersion]]
) -> SerializedAttributeVersion | None:
    required_attribute_path = (
        required_content_type.id,
        action_id,
        attribute_type.id
    )
    for versions in versions_by_model.values():
        for version in versions:
            if isinstance(version, SerializedAttributeVersion) and version.attribute_path == required_attribute_path:
                return version
    return None


def prepare_serialized_model_version(version: Version) -> SerializedVersion:
    serialized = SerializedVersion(
        type=version.content_type.model_class(),
        data=version.field_dict,
        str=version.object_repr,
    )
    if issubclass(version.content_type.model_class(), Attribute):
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
