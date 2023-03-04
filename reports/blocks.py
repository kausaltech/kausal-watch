from django.apps import apps
from django.db import models
from django.utils.functional import cached_property, lazy
from django.utils.translation import gettext_lazy as _
from typing import Tuple, Type
from wagtail.core import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLField, GraphQLForeignKey, GraphQLStreamfield, GraphQLString, GraphQLInt
from grapple.registry import registry as grapple_registry

from actions.models.action import Action
from actions.models.attributes import AttributeType, AttributeTypeQuerySet
from actions.models.category import Category, CategoryType
from actions.models.plan import Plan
from aplans.utils import underscore_to_camelcase


class ReportTypeChooserBlock(blocks.ChooserBlock):
    @cached_property
    def target_model(self):
        from .models import ReportType
        return ReportType

    @cached_property
    def widget(self):
        from .chooser import ReportTypeChooser
        return ReportTypeChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)




@register_streamfield_block
class ReportTypeFieldChooserBlock(blocks.CharBlock):
    # TODO: Write proper chooser block instead of extending CharBlock
    # Idea: Override CharBlock.__init__(), plug in widget to call of CharField.__init__(), set it to autocomplete widget. However, there are some issues with that regarding serialization to JSON.
    pass


@register_streamfield_block
class ReportComparisonBlock(blocks.StructBlock):
    report_type = ReportTypeChooserBlock(label=_('Report type'), required=True)
    report_field = ReportTypeFieldChooserBlock(label=_('UUID of report field'), required=True)

    def reports_to_compare(self, values):
        num_compare = 2  # TODO: Make this configurable in block
        report_type = values['report_type']
        reports = report_type.reports.order_by('-start_date')[:num_compare]
        return reports

    graphql_fields = [
        GraphQLForeignKey('report_type', 'reports.ReportType'),
        GraphQLString('report_field'),
        # For some reason GraphQLForeignKey strips the is_list argument, so we need to use GraphQLField directly here
        GraphQLField(
            'reports_to_compare',
            lambda: grapple_registry.models.get(apps.get_model('reports', 'Report')),
            is_list=True,
        ),
    ]


# FIXME: Use namespaces (packages) to avoid class names like this
@register_streamfield_block
class ActionTextAttributeTypeReportFieldBlock(blocks.StructBlock):
    # attribute_type = ActionAttributeTypeChooserBlock(required=True, label=_("Attribute type"))
    name = blocks.CharBlock(heading=_('Name'))
    identifier = blocks.CharBlock(heading=_('Identifier'))  # to be combined with report identifier

    # graphql_fields = []  # TODO
    attribute_type_format = AttributeType.AttributeFormat.TEXT

    class Meta:
        label = _("Text attribute")


@register_streamfield_block
class ActionImplementationPhaseReportFieldBlock(blocks.StaticBlock):
    class Meta:
        label = _("implementation phase")


@register_streamfield_block
class ReportFieldBlock(blocks.StreamBlock):
    # TODO: action status
    implementation_phase = ActionImplementationPhaseReportFieldBlock()
    text_attribute = ActionTextAttributeTypeReportFieldBlock()

    # graphql_types = []  # TODO
