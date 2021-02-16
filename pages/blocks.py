from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLImage, GraphQLPage, GraphQLStreamfield, GraphQLString
from grapple.registry import registry
from grapple.types.streamfield import ListBlock as GrappleListBlock, StructBlockItem
from uuid import UUID
from wagtail.core import blocks
from wagtail.images.blocks import ImageChooserBlock


class ListBlockWithIncrementingChildIds(GrappleListBlock):
    def resolve_items(self, info, **kwargs):
        # Grapple's ListBlock uses self.id also as IDs for the child blocks. We override this to make them unique.
        # FIXME: This causes problems if we rely on the IDs for anything else except uniqueness.
        block_type = self.block.child_block
        id = UUID(self.id).int
        result = []
        for item in self.value:
            id += 1
            result.append(StructBlockItem(str(UUID(int=id)), block_type, item))
        return result


registry.streamfield_blocks.update(
    {
        blocks.ListBlock: ListBlockWithIncrementingChildIds,
    }
)


@register_streamfield_block
class QuestionBlock(blocks.StructBlock):
    question = blocks.CharBlock(heading=_('Question'))
    answer = blocks.RichTextBlock(heading=_('Answer'))

    graphql_fields = [
        GraphQLString('question'),
        GraphQLString('answer'),
    ]


@register_streamfield_block
class QuestionAnswerBlock(blocks.StructBlock):
    heading = blocks.CharBlock(classname='title', heading=_('Title'), required=False)
    questions = blocks.ListBlock(QuestionBlock())

    graphql_fields = [
        GraphQLString('heading'),
        GraphQLStreamfield('questions'),
    ]


@register_streamfield_block
class FrontPageHeroBlock(blocks.StructBlock):
    layout = blocks.ChoiceBlock(choices=[
        ('big_image', _('Big image')),
        ('small_image', _('Small image')),
    ])
    image = ImageChooserBlock()
    heading = blocks.CharBlock(classname='full title', label=_('Heading'))
    lead = blocks.RichTextBlock(label=_('Lead'))

    graphql_fields = [
        GraphQLString('layout'),
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

    graphql_fields = [
        GraphQLString('text'),
        GraphQLPage('page'),
    ]
