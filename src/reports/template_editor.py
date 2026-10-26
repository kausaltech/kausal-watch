"""
Data for the drag-and-drop editor of a report template's fields (plan 3, Phase B).

The editor is part of the extensions. It reads the fields the template can have (the field bank) and the template's
current fields from the form, and writes them back into a hidden input in the format `ReportType.fields` stores, so
the template form saves and validates them like any other StreamField value.
"""

from __future__ import annotations

import json
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, Literal, NotRequired, TypedDict

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Max
from django.http import JsonResponse
from django.urls import reverse
from django.utils.text import capfirst
from django.utils.translation import get_language, gettext as _
from django.views import View
from wagtail.admin.panels import FieldPanel
from wagtail.blocks import BlockField

from kausal_common.users import user_or_bust

from actions.blocks.base import ActionReportContentField
from actions.models import Action, AttributeType, Plan
from admin_site.context_processors import i18n as admin_i18n_context
from orgs.models import Organization

if TYPE_CHECKING:
    from django.http import HttpRequest
    from wagtail.blocks import StreamBlock, StreamValue


CREATE_REPORTING_FIELD_URL_NAME = 'wagtailsnippets_reports_reporttype:create_reporting_field'

# The containing organization of a responsible party can be looked up this many levels down at most
MAX_TARGET_ANCESTOR_DEPTH = 10

type FieldGroup = Literal['builtin', 'category', 'reporting', 'custom']


class SettingOption(TypedDict):
    value: int | None
    label: str


class FieldSetting(TypedDict):
    name: str
    label: str
    options: list[SettingOption]
    default: int | None


class FieldDefinition(TypedDict):
    """A field that can be added to a report template, as the editor's field bank offers it."""

    key: str
    section: Literal['action']
    group: FieldGroup
    label: str
    blockType: str
    baseValue: dict[str, Any]
    settings: NotRequired[list[FieldSetting]]


def report_template_editor_available() -> bool:
    return find_spec('kausal_watch_extensions') is not None


def _definition(
    key: str, group: FieldGroup, label: str, block_type: str, base_value: dict[str, Any] | None = None
) -> FieldDefinition:
    return FieldDefinition(key=key, section='action', group=group, label=label, blockType=block_type, baseValue=base_value or {})


def _containing_organization_setting(plan: Plan) -> FieldSetting:
    depth = Organization.objects.available_for_plan(plan).aggregate(depth=Max('depth'))['depth'] or 1
    # A template may already use a level deeper than the plan's organizations go
    for report_type in plan.report_types.all():
        for child in report_type.fields or []:
            if child.block_type == 'responsible_parties' and child.value and child.value.get('target_ancestor_depth'):
                depth = max(depth, child.value['target_ancestor_depth'])
    levels = range(1, min(depth, MAX_TARGET_ANCESTOR_DEPTH) + 1)
    options = [SettingOption(value=None, label=_('Not included'))]
    options += [SettingOption(value=level, label=_('Level %(level)d') % {'level': level}) for level in levels]
    return FieldSetting(name='target_ancestor_depth', label=_('Containing organization'), options=options, default=None)


def get_report_field_definitions(plan: Plan, stream_block: StreamBlock) -> list[FieldDefinition]:
    """
    Return the fields the report templates of the plan can have.

    Every block type of `ReportFieldBlock` is offered once; attributes and categories once per attribute and category
    type of the plan. The labels are those the spreadsheet export heads the columns with.
    """
    definitions: list[FieldDefinition] = []
    for block_type, block in stream_block.child_blocks.items():
        if block_type in ('attribute', 'categories'):
            continue
        assert isinstance(block, ActionReportContentField)
        label = capfirst(block.xlsx_column_labels(block.get_default(), plan=plan)[0])
        definition = _definition(block_type, 'builtin', label, block_type)
        if block_type == 'responsible_parties':
            definition['settings'] = [_containing_organization_setting(plan)]
        definitions.append(definition)

    for category_type in plan.category_types.prefetch_related('levels').order_by('pk'):
        definition = _definition(
            f'categories:{category_type.pk}',
            'category',
            str(category_type.name_i18n),
            'categories',
            {'category_type': category_type.pk},
        )
        levels = list(category_type.levels.all())
        if levels:
            options = [SettingOption(value=None, label=_('Categories as assigned'))]
            options += [
                SettingOption(value=level.pk, label=str(level.name_i18n))  # type: ignore[attr-defined]
                for level in levels
            ]
            definition['settings'] = [
                FieldSetting(name='category_level', label=_('Category level'), options=options, default=None)
            ]
        definitions.append(definition)

    definitions.extend(
        _reporting_field_definition(attribute_type)
        for attribute_type in AttributeType.objects.for_actions(plan).order_by('order', 'pk')
    )
    return definitions


class ReportTemplateFieldsWidget(forms.Widget):
    """
    Edit `ReportType.fields` with the drag-and-drop editor instead of Wagtail's StreamField editor.

    The value travels as the JSON of the stream's prep value: a list of `{id, type, value}` children.
    """

    template_name = 'reports/widgets/report_template_fields.html'

    def __init__(self, stream_block: StreamBlock, plan: Plan, attrs: dict[str, Any] | None = None):
        super().__init__(attrs)
        self.stream_block = stream_block
        self.plan = plan

    def format_value(self, value: StreamValue | None) -> str:  # type: ignore[override]
        if value is None:
            return '[]'
        return json.dumps(self.stream_block.get_prep_value(value))

    def get_context(self, name: str, value: Any, attrs: dict[str, Any] | None) -> dict[str, Any]:
        context = super().get_context(name, value, attrs)
        widget_id = context['widget']['attrs'].get('id') or name
        context['editor_id'] = f'{widget_id}-editor'
        context['definitions_id'] = f'{widget_id}-definitions'
        context['definitions'] = get_report_field_definitions(self.plan, self.stream_block)
        context['editor_props'] = {
            'input_id': widget_id,
            'definitions_id': context['definitions_id'],
            'create_reporting_field_url': reverse(CREATE_REPORTING_FIELD_URL_NAME),
        }
        context['editor_props_id'] = f'{widget_id}-props'
        return context

    def value_from_datadict(self, data, files, name: str) -> StreamValue | None:
        raw = data.get(name)
        if raw is None:
            return None
        try:
            children = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(children, list):
            return None
        return self.stream_block.to_python(children)

    def value_omitted_from_data(self, data, files, name: str) -> bool:
        return name not in data


class ReportTemplateFieldsFormField(BlockField):
    """Edit `ReportType.fields` with `ReportTemplateFieldsWidget`."""

    def __init__(self, stream_block: StreamBlock, plan: Plan, **kwargs):
        kwargs.setdefault('widget', ReportTemplateFieldsWidget(stream_block, plan))
        super().__init__(block=stream_block, **kwargs)

    def clean(self, value):
        # The editor always sends a list; anything else has been tampered with or comes from a stale page
        if value is None:
            raise ValidationError(_('The fields could not be read. Reload the page and try again.'))
        return super().clean(value)


class ReportTemplateFieldsPanel(FieldPanel):
    """Mount the drag-and-drop editor on the `ReportTemplateFieldsWidget` of the fields."""

    class BoundPanel(FieldPanel.BoundPanel):
        template_name = 'reports/panels/report_template_fields_panel.html'

        def get_context_data(self, parent_context=None):
            context = super().get_context_data(parent_context)
            # The editor's mount script needs what the page's context processors provide, but Wagtail renders the
            # form's panels without the page's context
            input_id = self.bound_field.auto_id
            context.update(
                admin_i18n_context(self.request),
                LANGUAGE_CODE=get_language(),
                request=self.request,
                active_plan=user_or_bust(self.request.user).get_active_admin_plan(),
                editor_selector=f'#{input_id}-editor',
                editor_props_id=f'{input_id}-props',
            )
            return context


def _reporting_field_definition(attribute_type: AttributeType) -> FieldDefinition:
    return _definition(
        f'attribute:{attribute_type.pk}',
        'reporting' if attribute_type.show_in_reporting_tab else 'custom',
        str(attribute_type.name_i18n),
        'attribute',
        {'attribute_type': attribute_type.pk},
    )


class CreateReportingFieldView(View):
    """
    Define a new reporting field from the report template editor (plan 3, B3).

    The field is an ordinary text custom field of the plan's actions, shown in the actions' Reporting tab and only to
    logged-in users. It is created right away, before the template is saved: it belongs to the plan, not the template.
    """

    http_method_names = ['post']

    def post(self, request: HttpRequest) -> JsonResponse:
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()
        if not user.is_general_admin_for_plan(plan):
            raise PermissionDenied
        try:
            data = json.loads(request.body)
        except ValueError:
            return JsonResponse({'error': _('The field could not be read.')}, status=400)
        if not isinstance(data, dict):
            return JsonResponse({'error': _('The field could not be read.')}, status=400)
        name = str(data.get('name') or '').strip()
        help_text = str(data.get('help_text') or '').strip()
        if not name:
            return JsonResponse({'error': _('Enter a name for the field.')}, status=400)

        attribute_type = AttributeType(
            object_content_type=ContentType.objects.get_for_model(Action),
            scope_content_type=ContentType.objects.get_for_model(Plan),
            scope_id=plan.pk,
            name=name,
            help_text=help_text,
            format=AttributeType.AttributeFormat.TEXT,
            show_in_reporting_tab=True,
            instances_visible_for=AttributeType.VisibleFor.AUTHENTICATED,
            primary_language=plan.primary_language,
            other_languages=plan.other_languages or [],
        )
        try:
            attribute_type.full_clean()
        except ValidationError as e:
            return JsonResponse({'error': ' '.join(e.messages)}, status=400)
        attribute_type.save()
        return JsonResponse(_reporting_field_definition(attribute_type), status=201)
