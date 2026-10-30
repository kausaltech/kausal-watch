from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import apps
from django.core.exceptions import ValidationError
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.blocks.struct_block import StructBlockValidationError

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLField, GraphQLForeignKey, GraphQLString
from grapple.registry import registry as grapple_registry
from sentry_sdk import capture_message

from reports.blocks.choosers import ReportChooserBlock, ReportTypeChooserBlock, ReportTypeFieldChooserBlock

if TYPE_CHECKING:
    from reports.models import ReportType


def _has_snapshot_value(block) -> bool:
    """Whether the public API returns the field's values for an action (some fields only exist in exports)."""
    from reports.report_formatters import ReportFieldFormatter

    formatter = getattr(block, 'report_value_formatter', None)
    return formatter is not None and (
        type(formatter).value_for_action_snapshot is not ReportFieldFormatter.value_for_action_snapshot
    )


def comparable_fields(report_type: ReportType) -> list[tuple[str, str]]:
    """
    Return the ID and name of each field of the template that a comparison can show.

    The block is public, so only public action fields count, and only those whose values the public API returns.
    """
    fields: list[tuple[str, str]] = []
    for child in report_type.fields or []:
        if child.block_type == 'attribute':
            attribute_type = child.value['attribute_type']
            if attribute_type is None or attribute_type.instances_visible_for != attribute_type.VisibleFor.PUBLIC:
                continue
            label = str(attribute_type.name_i18n)
        elif _has_snapshot_value(child.block):
            # Labelled as the template editor and the spreadsheet export label it
            label = capfirst(child.block.xlsx_column_labels(child.value, plan=report_type.plan)[0])
        else:
            continue
        fields.append((str(child.id), label))
    return fields


@register_streamfield_block
class ReportComparisonBlock(blocks.StructBlock):
    report_type = ReportTypeChooserBlock(required=True)
    reports = blocks.ListBlock(
        ReportChooserBlock(),
        default=[],
        label=_('Reports'),
        help_text=_('The completed reports of the template to compare.'),
    )
    report_field = ReportTypeFieldChooserBlock(
        label=_('Field'),
        required=True,
        help_text=_('The field of the template whose values are compared. Only public fields can be compared.'),
    )

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
        if report_type is not None and result['report_field'] not in dict(comparable_fields(report_type)):
            message = _('Choose a public action field of the chosen template.')
            raise StructBlockValidationError({'report_field': ValidationError(message)})
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
