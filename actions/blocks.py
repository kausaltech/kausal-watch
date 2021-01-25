from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from wagtail.core.blocks import ChooserBlock, StructBlock, StaticBlock, ChoiceBlock

from .chooser import CategoryChooser
from .models import Category


class CategoryChooserBlock(ChooserBlock):
    @cached_property
    def target_model(self):
        return Category

    @cached_property
    def widget(self):
        return CategoryChooser

    class Meta:
        icon = "image"


class ActionHighlightsBlock(StaticBlock):
    pass


class ActionListBlock(StructBlock):
    category_filter = CategoryChooserBlock(label=_('Filter on category'))


class CategoryListBlock(StructBlock):
    style = ChoiceBlock(choices=[
        ('cards', _('Cards')),
        ('table', _('Table')),
    ])
