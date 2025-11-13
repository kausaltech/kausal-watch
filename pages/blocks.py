from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Callable, Literal, cast
from uuid import UUID

import graphene
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.embeds.embeds import get_embed, get_finder_for_embed
from wagtail.embeds.exceptions import EmbedUnsupportedProviderException
from wagtail.images.blocks import ImageChooserBlock

import sentry_sdk
from grapple.helpers import register_streamfield_block
from grapple.models import (
    GraphQLBoolean,
    GraphQLField,
    GraphQLForeignKey,
    GraphQLImage,
    GraphQLPage,
    GraphQLString,
)
from grapple.registry import registry
from grapple.types.streamfield import ListBlock as GrappleListBlock, StructBlockItem

from kausal_common.graphene.grapple import make_grapple_field

from aplans.utils import validate_json

from actions.blocks.choosers import CategoryChooserBlock
from actions.models.category import Category

if TYPE_CHECKING:
    from wagtail.embeds.models import Embed

    from aplans.graphql_types import GQLInfo


class ListBlockWithIncrementingChildIds(GrappleListBlock):
    @staticmethod
    def resolve_items(root: blocks.StreamValue.StreamChild, info, **kwargs) -> list[StructBlockItem]:
        # Grapple's ListBlock uses self.id also as IDs for the child blocks. We override this to make them unique.
        # FIXME: This causes problems if we rely on the IDs for anything else except uniqueness.
        block_type = cast('blocks.ListBlock', root.block).child_block
        id = cast('int', UUID(root.id).int)  # pyright: ignore[reportInvalidCast]
        result: list[StructBlockItem] = []
        for item in root.value:
            id += 1
            result.append(StructBlockItem(str(UUID(int=id)), block_type, item))
        return result


registry.streamfield_blocks.update(
    {
        blocks.ListBlock: ListBlockWithIncrementingChildIds,
    },
)


@register_streamfield_block
class QuestionBlock(blocks.StructBlock):
    question = blocks.CharBlock(heading=_('Question'))
    answer = blocks.RichTextBlock(heading=_('Answer'))

    class Meta:
        label = _('Question')

    graphql_fields = [
        GraphQLString('question', required=True),
        GraphQLString('answer', required=True),
    ]


RESPONSIVE_STYLES = {
    's': 'responsive-object-small',
    'm': 'responsive-object-medium',
    'l': 'responsive-object-large',
}


IFRAME_SRC_RE = re.compile(r'src="([^"]+)"')


def sanitize_iframe(embed_contents: str) -> str:
    """Try to extract only URL part if complete iframe tag was used."""
    if not embed_contents.startswith('<iframe'):
        return embed_contents
    match = IFRAME_SRC_RE.search(embed_contents)
    if not match:
        return embed_contents
    return match.group(1)


class EmbedHTMLValue(graphene.ObjectType[Any]):
    html: graphene.String = graphene.String()

    @staticmethod
    def resolve_html(parent: dict[Literal['height', 'url'], str], _info: GQLInfo) -> str:
        height_key = parent['height']
        url = parent['url']
        css_class = RESPONSIVE_STYLES.get(height_key, next(iter(RESPONSIVE_STYLES.values())))
        try:
            embed: Embed = get_embed(url)
        except EmbedUnsupportedProviderException as exception:
            _ = sentry_sdk.capture_exception(exception)
            return '<div data-error="unsupported-embed-provider"></div>'
        return f"<div data-embed-provider='{embed.provider_name}' class='responsive-object {css_class}'>{embed.html}</div>"


@register_streamfield_block
class AdaptiveEmbedBlock(blocks.StructBlock):
    # Note: Do not try to use Wagtail's EmbedBlock here.
    # It doesn't support dynamic, configurable sizes.
    # The extra inner field is just to enable the custom
    # resolve_html method
    embed: blocks.StructBlock = blocks.StructBlock(
        [('url', blocks.CharBlock(label=_('URL'))),
         # The height value is actually used as a generic size parameter whose interpretation dependends on
         # the type of embed (the provider)
         ('height', blocks.ChoiceBlock(
             choices=[('s', _('small')), ('m', _('medium')), ('l', _('large'))],
             label=_('Size'),
         ))],
    )
    full_width: blocks.BooleanBlock = blocks.BooleanBlock(required=False)

    def clean(self, value: dict[str, Any]):
        result = super().clean(value)
        url = result.get('embed', {}).get('url')
        if url and len(url):
            result['embed']['url'] = sanitize_iframe(url)
        url = result.get('embed', {}).get('url')
        try:
            get_finder_for_embed(url)
        except EmbedUnsupportedProviderException as e:
            raise ValidationError(_("The source URL of the embed is invalid or not supported.")) from e
        return result

    class Meta:
        label = _('Embed')

    graphql_fields = [
        GraphQLField('embed', EmbedHTMLValue),
        GraphQLBoolean('full_width'),
    ]

@register_streamfield_block
class RawVisualizationBlock(blocks.TextBlock):
    def __init__(self,
        required: bool = True,
        help_text: str | None = None,
        rows: int = 1,
        max_length: int | None = None,
        min_length: int | None = None,
        search_index: bool = True,
        validators: tuple[Callable[[str], None]] = (validate_json,),
        **kwargs: dict[str, Any],
    ):
        super().__init__(
            required=required,
            help_text=help_text,
            rows=rows,
            max_length=max_length,
            min_length=min_length,
            search_index=search_index,
            validators=validators,
            **kwargs,
        )


@register_streamfield_block
class QuestionAnswerBlock(blocks.StructBlock):
    heading = blocks.CharBlock(classname='title', heading=_('Title'), required=False)
    questions = blocks.ListBlock(QuestionBlock())

    class Meta:
        label = _('Questions & Answers')

    graphql_fields = [
        GraphQLString('heading'),
        make_grapple_field('questions', QuestionBlock, is_list=True, required=True),
    ]


@register_streamfield_block
class FrontPageHeroBlock(blocks.StructBlock):
    layout = blocks.ChoiceBlock(choices=[
        ('big_image', _('Big image')),
        ('small_image', _('Small image')),
    ])
    image = ImageChooserBlock(label=_('Image'))
    heading = blocks.CharBlock(classname='full title', label=_('Heading'), required=False)
    lead = blocks.RichTextBlock(label=_('Lead'), required=False)

    class Meta:
        label = _('Front page hero block')

    graphql_fields = [
        GraphQLString('layout', required=True),
        GraphQLImage('image'),
        GraphQLString('heading'),
        GraphQLString('lead'),
    ]


@register_streamfield_block
class PageLinkBlock(blocks.StructBlock):
    text = blocks.CharBlock(required=False)
    page = blocks.PageChooserBlock(required=False)
    # FIXME: `page` should be required, but so far the only use for PageLinkBlock is in IndicatorShowcaseBlock, where
    # the entire PageLinkBlock should be optional. It is, however, not easily possible to make a StructBlock optional:
    # https://github.com/wagtail/wagtail/issues/2665

    class Meta:
        label = _('Page link')

    graphql_fields = [
        GraphQLString('text'),
        GraphQLPage('page'),
    ]


@register_streamfield_block
class CardBlock(blocks.StructBlock):
    image = ImageChooserBlock(required=False)
    heading = blocks.CharBlock()
    content = blocks.CharBlock(required=False)
    # FIXME: We should also be able to choose internal pages
    link = blocks.CharBlock(required=False)

    class Meta:
        label = _('Card')

    graphql_fields = [
        GraphQLImage('image'),
        GraphQLString('heading'),
        GraphQLString('content'),
        GraphQLString('link'),
    ]


@register_streamfield_block
class CardListBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    lead = blocks.CharBlock(required=False)
    cards = blocks.ListBlock(CardBlock())

    class Meta:
        label = _('Cards')

    graphql_fields = [
        GraphQLString('heading'),
        GraphQLString('lead'),
        make_grapple_field('cards', CardBlock, is_list=True, required=True),
    ]


@register_streamfield_block
class ActionCategoryFilterCardBlock(blocks.StructBlock):
    heading = blocks.CharBlock(label=_('Heading'))
    lead = blocks.CharBlock(label=_('Lead'))
    category = CategoryChooserBlock()

    class Meta:
        # FIXME: The label (and class name) is probably misleading
        label = _('Action category filter card')

    graphql_fields = [
        GraphQLString('heading'),
        GraphQLString('lead'),
        GraphQLForeignKey('category', Category, required=True),
    ]


@register_streamfield_block
class ActionCategoryFilterCardsBlock(blocks.StructBlock):
    cards = blocks.ListBlock(ActionCategoryFilterCardBlock(), label=_('Links'))

    class Meta:
        # FIXME: The label (and class name) is probably misleading
        label = _('Action category filter cards')

    graphql_fields = [
        make_grapple_field('cards', ActionCategoryFilterCardBlock, is_list=True, required=True),
    ]


@register_streamfield_block
class AccessibilityStatementComplianceStatusBlock(blocks.StaticBlock):
    class Meta:
        label = _('Accessibility statement compliance status')


@register_streamfield_block
class AccessibilityStatementPreparationInformationBlock(blocks.StaticBlock):
    class Meta:
        label = _('Accessibility statement preparation information')


@register_streamfield_block
class AccessibilityStatementContactInformationBlock(blocks.StructBlock):
    publisher_name = blocks.CharBlock(label=_('Publisher name'))
    maintenance_responsibility_paragraph = blocks.CharBlock(
        required=False, label=_('Maintenance responsibility paragraph'),
        help_text=_('If this is set, it will be displayed instead of "This service is published by [publisher]".'),
    )
    email = blocks.CharBlock(label=_('Email address'))

    graphql_fields = [
        GraphQLString('publisher_name', required=True),
        GraphQLString('maintenance_responsibility_paragraph', required=False),
        GraphQLString('email', required=True),
    ]

    class Meta:
        label = _('Accessibility statement contact information')


@register_streamfield_block
class AccessibilityStatementContactFormBlock(blocks.StaticBlock):
    class Meta:
        label = _('Accessibility statement contact form')


@register_streamfield_block
class ActionStatusGraphsBlock(blocks.StaticBlock):
    class Meta:
        label = _('Action status pie charts')


@register_streamfield_block
class LargeImageBlock(blocks.StructBlock):
    image = ImageChooserBlock(label=_('Image'))
    width = blocks.ChoiceBlock(
        label=_('Width'),
        choices=[
            ('maximum', _('Maximum')),
            ('fit_to_column', _('Fit to column')),
        ],
        default='maximum',
    )

    class Meta:
        label = _('Large image')

    graphql_fields = [
        GraphQLImage('image'),
        GraphQLString('width'),
    ]
