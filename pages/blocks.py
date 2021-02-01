from django.utils.translation import gettext_lazy as _
from wagtail.core import blocks
from wagtail.images.blocks import ImageChooserBlock


class QuestionAnswerBlock(blocks.StructBlock):
    heading = blocks.CharBlock(classname='title', heading=_('Title'))
    questions = blocks.ListBlock(blocks.StructBlock([
        ('question', blocks.CharBlock(heading=_('Question'))),
        ('answer', blocks.RichTextBlock(heading=_('Answer'))),
    ]), heading=_('Questions'))


class FrontPageHeroBlock(blocks.StructBlock):
    layout = blocks.ChoiceBlock(choices=[
        ('big_image', _('Big image')),
        ('small_image', _('Small image')),
    ])
    image = ImageChooserBlock()
    heading = blocks.CharBlock(classname='full title', label=_('Heading'))
    lead = blocks.RichTextBlock(label=_('Lead'))
