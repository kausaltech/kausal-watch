import sentry_sdk
import graphene
from graphql.error import GraphQLError
from wagtail.images.models import SourceImageIOError

from aplans.graphql_types import DjangoNode, replace_image_node
import graphene_django_optimizer as gql_optimizer


from .models import AplansImage, AplansRendition


class ImageRendition(DjangoNode):
    id = graphene.ID(required=True)
    src = graphene.String(required=True)
    width = graphene.Int(required=True)
    height = graphene.Int(required=True)
    alt = graphene.String(required=True)

    def resolve_id(root, info):
        return root.id

    class Meta:
        model = AplansRendition
        fields = [
            'id', 'src', 'width', 'height', 'alt',
        ]


@replace_image_node
class ImageNode(DjangoNode):
    rendition = graphene.Field(
        ImageRendition,
        size=graphene.String(),
        crop=graphene.Boolean(required=False, default_value=True)
    )

    class Meta:
        model = AplansImage
        fields = [
            'id', 'title', 'focal_point_x', 'focal_point_y', 'focal_point_width',
            'focal_point_height', 'height', 'width', 'image_credit', 'alt_text'
        ]

    @gql_optimizer.resolver_hints(
        prefetch_related=('renditions',)
    )
    def resolve_rendition(root: AplansImage, info, size=None, crop=True):
        if size is not None:
            try:
                width, height = size.split('x')
            except Exception:
                raise GraphQLError('invalid size (should be <width>x<height>)')

            try:
                width = int(width)
                if width <= 100 or width > 1600:
                    raise Exception()
            except Exception:
                raise GraphQLError('invalid width: %d' % width)

            try:
                height = int(height)
                if height <= 100 or height > 1600:
                    raise Exception()
            except Exception:
                raise GraphQLError('invalid height: %d' % height)
            size = '%dx%d' % (width, height)
        else:
            size = '800x600'

        try:
            if crop:
                format_str = 'fill-%s-c50' % size
            else:
                format_str = 'max-%s' % size
            rendition = root.get_rendition(format_str)
        except (FileNotFoundError, SourceImageIOError) as e:
            # We ignore the error so that the query will not fail, but report it to
            # Sentry anyway.
            sentry_sdk.capture_exception(e)
            return None

        return ImageRendition(id=rendition.id, **rendition.get_fqdn_attrs(info.context))
