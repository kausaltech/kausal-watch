from django.apps import apps
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.blocks.struct_block import StructBlockValidationError

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLField, GraphQLForeignKey, GraphQLString
from grapple.registry import registry as grapple_registry
from sentry_sdk import capture_message

from reports.blocks.choosers import ReportChooserBlock, ReportTypeChooserBlock, ReportTypeFieldChooserBlock


@register_streamfield_block
class ReportComparisonBlock(blocks.StructBlock):
    report_type = ReportTypeChooserBlock(required=True)
    reports = blocks.ListBlock(
        ReportChooserBlock(),
        default=[],
        label=_('Reports'),
        help_text=_('The completed reports of the template to compare.'),
    )
    report_field = ReportTypeFieldChooserBlock(label=_('UUID of report field'), required=True)

    class Meta:
        label = _('Report comparison')

    def clean(self, value):
        result = super().clean(value)
        report_type = result['report_type']
        for report in result['reports']:
            if report is None:
                continue
            if report_type is not None and report.type_id != report_type.pk:
                message = _('"%(report)s" is not a report of the chosen template.') % {'report': report.name}
            elif not report.is_complete:
                message = _('"%(report)s" is not complete. Only completed reports can be compared.') % {'report': report.name}
            else:
                continue
            raise StructBlockValidationError({'reports': ValidationError(message)})
        return result

    def reports_to_compare(self, info, values):
        report_type = values['report_type']
        if report_type is None:
            # The report type has been deleted since the block was saved
            capture_message('Report comparison block refers to a missing report type', level='warning')
            return []
        # Chosen reports that have since been deleted are None
        return [report for report in values.get('reports') or [] if report is not None and report.type_id == report_type.pk]

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
