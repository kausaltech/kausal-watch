from django import forms
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block


class ReportTypeChooserBlock(blocks.ChooserBlock):
    class Meta:
        label = _('Report template')

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


class ReportChooserBlock(blocks.ChooserBlock):
    class Meta:
        label = _('Report')

    @cached_property
    def target_model(self):
        from reports.models import Report

        return Report

    @cached_property
    def widget(self):
        from reports.chooser import ReportChooser

        return ReportChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class ReportTypeFieldSelect(forms.Widget):
    """
    A dropdown of the custom fields of the report template chosen next to it in the same block.

    The value is kept in a hidden input, because the options are only known once the template is: the dropdown loads
    them whenever the template changes.
    """

    class Media:
        js = ('reports/report-field-select.js',)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}
        return format_html(
            '<div data-controller="report-field-select" data-report-field-select-url-value="{}"'
            ' data-report-field-select-empty-label-value="{}">'
            '<input type="hidden" name="{}" value="{}" data-report-field-select-target="input">'
            '<select id="{}" data-report-field-select-target="select"'
            ' data-action="report-field-select#choose" disabled></select></div>',
            reverse('wagtailsnippets_reports_reporttype:report_field_options'),
            _('Choose a field'),
            name,
            value or '',
            attrs.get('id', ''),
        )


@register_streamfield_block
class ReportTypeFieldChooserBlock(blocks.CharBlock):
    """The ID of a custom field in a report template, stored as text and chosen from the template's fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.field.widget = ReportTypeFieldSelect()

    class Meta:
        label = _('Report template field')
