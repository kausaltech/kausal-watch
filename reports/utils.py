from django.contrib.contenttypes.models import ContentType
from modelcluster.fields import ParentalManyToManyDescriptor

from actions.models.attributes import AttributeTypeChoiceOption
from actions.models.attributes import Attribute


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
        versions: list[dict]
):
    required_attribute_path = (
        required_content_type.id,
        action_id,
        attribute_type.id
    )
    for model, versions in versions.items():
        for version in versions:
            if version['attribute_path'] == required_attribute_path:
                return version
    return None


def prepare_serialized_model_version(version):
    attribute_path = None
    if issubclass(version.content_type.model_class(), Attribute):
        attribute_path = make_attribute_path(version.field_dict)
    return dict(
        type=version.content_type.model_class(),
        data=version.field_dict,
        str=version.object_repr,
        attribute_path=attribute_path
    )


def group_by_model(serialized_versions: list[dict]):
    result = {}
    for version in serialized_versions:
        _cls = version['type']
        result.setdefault(_cls, [])
        result[_cls].append(version)
    return result
