import graphene
from graphql.error import GraphQLError

from aplans.graphql_types import DjangoNode
from .models import AplansImage


class ImageRendition(graphene.ObjectType):
    src = graphene.String(required=True)
    width = graphene.Int(required=True)
    height = graphene.Int(required=True)
    alt = graphene.String(required=True)


class ImageNode(DjangoNode):
    rendition = graphene.Field(ImageRendition, required=True, size=graphene.String())

    class Meta:
        model = AplansImage
        only_fields = [
            'id', 'title'
        ]

    def resolve_rendition(self, info, size=None):
        if size is not None:
            try:
                width, height = size.split('x')
            except Exception:
                raise GraphQLError('invalid size (should be <width>x<height>)', [info])

            try:
                width = int(width)
                if width <= 100 or width > 1200:
                    raise Exception()
            except Exception:
                raise GraphQLError('invalid width: %d' % width, [info])

            try:
                height = int(height)
                if height <= 100 or height > 1200:
                    raise Exception()
            except Exception:
                raise GraphQLError('invalid height: %d' % height, [info])
            size = '%dx%d' % (width, height)
        else:
            size = '800x600'

        rendition = self.get_rendition('fill-%s-c50' % size)
        return ImageRendition(**rendition.get_fqdn_attrs(info.context))
