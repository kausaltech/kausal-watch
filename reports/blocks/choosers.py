from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block


class ReportTypeChooserBlock(blocks.ChooserBlock):
    class Meta:
        label = _('Report type')

    @cached_property
    def target_model(self):
        from reports.models import ReportType

        return ReportType

    @cached_property
    def widget(self):
        from reports.chooser import ReportTypeChooser

        return ReportTypeChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


@register_streamfield_block
class ReportTypeFieldChooserBlock(blocks.CharBlock):
    # TODO: Write proper chooser block instead of extending CharBlock
    # Idea: Override CharBlock.__init__(), plug in a widget to call from
    # CharField.__init__(), and set it to autocomplete. Serialization to JSON
    # makes this awkward, though.
    class Meta:
        label = _('Report type field')
