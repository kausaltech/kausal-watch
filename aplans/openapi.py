from drf_spectacular.openapi import AutoSchema as OpenAPIAutoSchema
from rest_framework import serializers


class AutoSchema(OpenAPIAutoSchema):
    def _get_serializer_field_meta(self, field, direction):
        # superclass function does not set title if the field label is a
        # "trivial string variation" of the field name. Work around
        # that by always setting title if field has a label.
        meta = super()._get_serializer_field_meta(field, direction)
        if 'title' in meta or not isinstance(field, serializers.Field):
            return meta
        if field.label:
            meta['title'] = str(field.label)
        return meta
