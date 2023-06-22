from django.contrib.contenttypes.models import ContentType
from modelcluster.fields import ParentalManyToManyDescriptor

from actions.models.attributes import AttributeTypeChoiceOption


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
    for version in versions:
        if version['attribute_path'] == required_attribute_path:
            return version
            # field_dict = {}
            # for field_name, value in version.field_dict.items():
            #     field = getattr(model, field_name)
            #     if isinstance(field, ParentalManyToManyDescriptor):
            #         # value should be a list of PKs of the related model; transform it to a list of instances
            #         related_model = field.rel.model
            #         value = [related_model.objects.get(pk=pk) for pk in value]
            #         field_dict[field_name] = value
            #         # This does not work for model fields that are a ManyToManyDescriptor. In such cases, you may want
            #         # to make the model a ClusterableModel and use, e.g., ParentalManyToManyField instead of
            #         # ManyToManyField.
            # instance = model(**field_dict)
            # return instance
    return None
