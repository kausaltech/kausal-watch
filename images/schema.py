import sentry_sdk
import graphene
from graphql.error import GraphQLError
from wagtail.images.models import SourceImageIOError

from aplans.graphql_types import DjangoNode, replace_image_node

from .models import AplansImage, AplansRendition


class ImageRendition(DjangoNode):
    src = graphene.String(required=True)
    width = graphene.Int(required=True)
    height = graphene.Int(required=True)
    alt = graphene.String(required=True)

    class Meta:
        model = AplansRendition
        fields = [
            'src', 'width', 'height', 'alt',
        ]


@replace_image_node
class ImageNode(DjangoNode):
    rendition = graphene.Field(ImageRendition, size=graphene.String())

    class Meta:
        model = AplansImage
        fields = [
            'id', 'title', 'focal_point_x', 'focal_point_y', 'focal_point_width',
            'focal_point_height', 'height', 'width', 'image_credit', 'alt_text'
        ]

    def resolve_rendition(self, info, size=None):
        if size is not None:
            try:
                width, height = size.split('x')
            except Exception:
                raise GraphQLError('invalid size (should be <width>x<height>)', [info])

            try:
                width = int(width)
                if width <= 100 or width > 1600:
                    raise Exception()
            except Exception:
                raise GraphQLError('invalid width: %d' % width, [info])

            try:
                height = int(height)
                if height <= 100 or height > 1600:
                    raise Exception()
            except Exception:
                raise GraphQLError('invalid height: %d' % height, [info])
            size = '%dx%d' % (width, height)
        else:
            size = '800x600'

        try:
            rendition = self.get_rendition('fill-%s-c50' % size)
        except (FileNotFoundError, SourceImageIOError) as e:
            # We ignore the error so that the query will not fail, but report it to
            # Sentry anyway.
            sentry_sdk.capture_exception(e)
            return None

        return ImageRendition(**rendition.get_fqdn_attrs(info.context))
