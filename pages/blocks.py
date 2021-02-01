from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLStreamfield, GraphQLString

from wagtail.core import blocks
from wagtail.images.blocks import ImageChooserBlock


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
