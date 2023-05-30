from django.contrib.contenttypes.models import ContentType
from modelcluster.fields import ParentalManyToManyDescriptor
from reversion.models import Version

from actions.models import Action


def get_attribute_for_type_from_related_objects(action_id: int, attribute_type, versions: list[Version]):
    pattern = {
        'type_id': attribute_type.id,
        'content_type_id': ContentType.objects.get_for_model(Action).id,
        'object_id': action_id
    }

    for version in versions:
        model = version['type']
        # FIXME: It would be safer if there were a common base class for all (and only for) attribute models
        if (model.__module__ == 'actions.models.attributes'
                and all(version['data'].get(key) == value for key, value in pattern.items())):
            # Replace PKs by model instances. (We assume they still exist in the DB, otherwise we are fucked.)
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
