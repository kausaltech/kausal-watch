from django.apps import apps
from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLField, GraphQLForeignKey, GraphQLString
from grapple.registry import registry as grapple_registry

from reports.blocks.choosers import ReportTypeChooserBlock, ReportTypeFieldChooserBlock


@register_streamfield_block
class ReportComparisonBlock(blocks.StructBlock):
    report_type = ReportTypeChooserBlock(required=True)
    report_field = ReportTypeFieldChooserBlock(label=_('UUID of report field'), required=True)

    class Meta:
        label = _('Report comparison')

    def reports_to_compare(self, info, values):
        max_reports_to_compare = 5  # TODO: Make this configurable in block
        report_type = values['report_type']
        reports = report_type.reports.filter(is_public=True).order_by('-start_date')[:max_reports_to_compare]
        return reports

    graphql_fields = [
        GraphQLForeignKey('report_type', 'reports.ReportType'),
        GraphQLString('report_field'),
        # For some reason GraphQLForeignKey strips the is_list argument, so we need to use GraphQLField directly here
        GraphQLField(
            'reports_to_compare',
            lambda: grapple_registry.models[apps.get_model('reports', 'Report')],  # pyright: ignore[reportUnknownLambdaType]
            is_list=True,
        ),
    ]
