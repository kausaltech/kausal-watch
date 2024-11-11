from __future__ import annotations

from django.apps import apps
from django.db import models
from django.utils.functional import lazy
from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLString

from aplans.graphql_interfaces import FieldBlockMetaInterface
from aplans.utils import StaticBlockToStructBlockWorkaroundMixin, underscore_to_camelcase

from reports.report_formatters import ActionReportContentField


def get_field_label(model: type[models.Model], field_name: str) -> str | None:
    if not apps.ready:
        return 'label'
    field = model._meta.get_field(field_name)
    if isinstance(field, (models.ForeignObjectRel,)):
        # It's a relation field
        label = str(field.related_model._meta.verbose_name_plural).capitalize()
    else:
        label = str(field.verbose_name).capitalize()
    return label


lazy_field_label = lazy(get_field_label, str)


class ActionListContentBlock(StaticBlockToStructBlockWorkaroundMixin, blocks.StructBlock):
    block_label: str

    field_label = blocks.CharBlock(
        required=False,
        help_text=_("Heading to show instead of the default"),
        default='',
        label=_("Field label"),
    )

    field_help_text = blocks.CharBlock(
        required=False,
        help_text=_("Help text for the field to be shown in the UI"),
        default='',
        label = _("Help text"),
    )

    graphql_fields = [
        GraphQLString('field_label'),
        GraphQLString('field_help_text'),
    ]

    def get_admin_text(self):
        return _("Content block: %(label)s") % dict(label=self.label)


def _get_default_block_class_name_(model: type[models.Model], field_name: str) -> str:
    camel_field = underscore_to_camelcase(field_name)
    class_name = '%s%sBlock' % (model._meta.object_name, camel_field)
    return class_name


def generate_block_for_field(
        model: type[models.Model],
        field_name: str,
        params: dict | None = None,
        superclasses: tuple[type[blocks.Block], ...] = (
            ActionListContentBlock,
            ActionReportContentField,
        ),
        class_name: str | None = None,
):
    if params is None:
        params = dict()
    if class_name is None:
        class_name = _get_default_block_class_name_(model, field_name)

    # Fields need to be evaluated lazily, because when this function is called,
    # the model registry is not yet fully initialized.
    label = params.get('label') or lazy_field_label(model, field_name)
    meta = type(
        'Meta', (), {
            'label': label,
            'field_name': field_name,
        },
    )

    attrs = {
        'Meta': meta,
        '__module__': __name__,
        'graphql_interfaces': (FieldBlockMetaInterface, ),
    }
    if 'report_value_formatter_class' in params:
        attrs['report_value_formatter_class'] = params['report_value_formatter_class']

    klass = type(class_name, superclasses, attrs)
    register_streamfield_block(klass)
    return klass
