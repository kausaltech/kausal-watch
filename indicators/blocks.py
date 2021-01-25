from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from wagtail.core.blocks import ChooserBlock, StaticBlock, StructBlock, ChoiceBlock
from django.utils.html import format_html

from .chooser import IndicatorChooser
from .models import Indicator


class IndicatorChooserBlock(ChooserBlock):
    @cached_property
    def target_model(self):
        return Indicator

    @cached_property
    def widget(self):
        return IndicatorChooser

    def render_basic(self, value, context=None):
        print('render basic called %s' % value)
        if value:
            return format_html('<a href="{0}">{1}</a>', '', value.name)
        else:
            return ''

    class Meta:
        icon = "image"
        label = _('Indicator')


class IndicatorHighlightsBlock(StaticBlock):
    pass


class IndicatorBlock(StructBlock):
    label = _('Indicator')
    indicator = IndicatorChooserBlock(label=_('Indicator'))
    style = ChoiceBlock(choices=[
        ('graph', _('Graph')),
        ('progress', _('Progress')),
        ('animated', _('Animated')),
    ])
