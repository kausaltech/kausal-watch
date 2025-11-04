from __future__ import annotations

from typing import TYPE_CHECKING

import graphene
from django.db.models.query import Prefetch
from graphql.error import GraphQLError
from wagtail.images.models import SourceImageIOError

import graphene_django_optimizer as gql_optimizer
import sentry_sdk

from aplans.graphql_types import DjangoNode, replace_image_node

from .models import AplansImage, AplansRendition

if TYPE_CHECKING:
    from aplans.graphql_types import GQLInfo


@replace_image_node
class ImageRendition(DjangoNode[AplansRendition]):
    id = graphene.ID(required=True)
    src = graphene.String(required=True)
    width = graphene.Int(required=True)
    height = graphene.Int(required=True)
    alt = graphene.String(required=True)

    class Meta:
        model = AplansRendition
        fields = [
            'id', 'src', 'width', 'height', 'alt',
        ]

    # needed for grapple
    @classmethod
    def type(cls) -> dict:
        return dict(lazy=False)


@replace_image_node
class ImageNode(DjangoNode[AplansImage]):
    rendition = graphene.Field(
        ImageRendition,
        size=graphene.String(),
        crop=graphene.Boolean(required=False, default_value=True),
    )

    class Meta:
        model = AplansImage
        fields = [
            'id', 'title', 'focal_point_x', 'focal_point_y', 'focal_point_width',
            'focal_point_height', 'height', 'width', 'image_credit', 'alt_text',
        ]

    # needed for grapple
    @classmethod
    def type(cls) -> dict:
        return dict(lazy=False)

    @gql_optimizer.resolver_hints(
        prefetch_related=(Prefetch('renditions', to_attr='prefetched_renditions'),),
    )
    @staticmethod
    def resolve_rendition(root: AplansImage, info: GQLInfo, size: str | None = None, crop: bool = True) -> None | ImageRendition:
        if size is not None:
            try:
                width_str, height_str = size.split('x')
            except Exception:
                raise GraphQLError('invalid size (should be <width>x<height>)', nodes=info.field_nodes) from None

            try:
                width = int(width_str)
                if width <= 100 or width > 1600:
                    raise Exception()  # noqa: TRY301
            except Exception:
                raise GraphQLError('invalid width: %d' % width, nodes=info.field_nodes) from None

            try:
                height = int(height_str)
                if height <= 100 or height > 1600:
                    raise Exception()  # noqa: TRY301
            except Exception:
                raise GraphQLError('invalid height: %d' % height, nodes=info.field_nodes) from None
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

        return ImageRendition(id=rendition.pk, **rendition.get_fqdn_attrs(info.context))
