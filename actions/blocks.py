from typing import Tuple, Type

from django.apps import apps
from django.db import models
from django.utils.functional import cached_property, lazy
from django.utils.translation import gettext_lazy as _
from wagtail.core import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString

from actions.models.action import Action
from actions.models.attributes import AttributeType, AttributeTypeQuerySet
from actions.models.category import CategoryType
from actions.models.plan import Plan
from aplans.utils import underscore_to_camelcase

from .chooser import AttributeTypeChooser, CategoryChooser, CategoryTypeChooser
from .models import Category


class CategoryChooserBlock(blocks.ChooserBlock):
    @cached_property
    def target_model(self):
        return Category

    @cached_property
    def widget(self):
        return CategoryChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class CategoryTypeChooserBlock(blocks.ChooserBlock):
    @cached_property
    def target_model(self):
        return CategoryType

    @cached_property
    def widget(self):
        return CategoryTypeChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class AttributeTypeChooserBlock(blocks.ChooserBlock):
    @cached_property
    def target_model(self):
        return AttributeType

    @cached_property
    def widget(self):
        return AttributeTypeChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class ActionAttributeTypeChooserBlock(AttributeTypeChooserBlock):
    @cached_property
    def widget(self):
        return AttributeTypeChooser(scope='action')


class CategoryAttributeTypeChooserBlock(AttributeTypeChooserBlock):
    # FIXME: Add support for limiting to one CategoryType

    @cached_property
    def widget(self):
        return AttributeTypeChooser(scope='category')


@register_streamfield_block
class ActionHighlightsBlock(blocks.StaticBlock):
    pass


@register_streamfield_block
class ActionListBlock(blocks.StructBlock):
    category_filter = CategoryChooserBlock(label=_('Filter on category'))

    graphql_fields = [
        GraphQLForeignKey('category_filter', Category),
    ]


@register_streamfield_block
class CategoryListBlock(blocks.StructBlock):
    category_type = CategoryTypeChooserBlock(label=_('Category type'), required=False)
    heading = blocks.CharBlock(classname='full title', label=_('Heading'), required=False)
    lead = blocks.RichTextBlock(label=_('Lead'), required=False)
    style = blocks.ChoiceBlock(choices=[
        ('cards', _('Cards')),
        ('table', _('Table')),
    ])

    graphql_fields = [
        GraphQLForeignKey('category_type', CategoryType),
        GraphQLString('heading'),
        GraphQLString('lead'),
        GraphQLString('style'),
    ]


@register_streamfield_block
class CategoryTreeMapBlock(blocks.StructBlock):
    heading = blocks.CharBlock(classname='full title', label=_('Heading'), required=False)
    lead = blocks.RichTextBlock(label=_('Lead'), required=False)

    category_type = CategoryTypeChooserBlock(label=_('Category type'), required=True)
    value_attribute = CategoryAttributeTypeChooserBlock(label=_('Value attribute'), required=True)

    graphql_fields = [
        GraphQLForeignKey('category_type', CategoryType),
        GraphQLForeignKey('value_attribute', AttributeType),
        GraphQLString('heading'),
        GraphQLString('lead'),
    ]


@register_streamfield_block
class RelatedPlanListBlock(blocks.StaticBlock):
    pass


@register_streamfield_block
class ActionAttributeTypeFilterBlock(blocks.StructBlock):
    attribute_type = ActionAttributeTypeChooserBlock(required=True)
    show_all_label = blocks.CharBlock(required=False)

    graphql_fields = [
        GraphQLString('show_all_label'),
        GraphQLForeignKey('attribute_type', AttributeType)
    ]


@register_streamfield_block
class CategoryTypeFilterBlock(blocks.StructBlock):
    style = blocks.ChoiceBlock(choices=[
        ('dropdown', _('Dropdown')),
        ('buttons', _('Buttons')),
    ])
    show_all_label = blocks.CharBlock(required=False)
    category_type = CategoryTypeChooserBlock(required=True)

    graphql_fields = [
        GraphQLString('style'),
        GraphQLString('show_all_label'),
        GraphQLForeignKey('category_type', CategoryType)
    ]


class FilterBlock(blocks.StaticBlock):
    filter_label: str
    graphql_fields = []

    def get_admin_text(self):
        return _("Filter: %(filter_label)s") % dict(filter_label=self.filter_label)


@register_streamfield_block
class ResponsiblePartyFilterBlock(FilterBlock):
    filter_label = _("responsible party")


@register_streamfield_block
class PrimaryOrganizationFilterBlock(FilterBlock):
    filter_label = _("primary organization")


@register_streamfield_block
class ActionImplementationPhaseFilterBlock(FilterBlock):
    filter_label = _("implementation phase")


@register_streamfield_block
class ActionScheduleFilterBlock(FilterBlock):
    filter_label = _("schedule")


@register_streamfield_block
class ActionListFilterBlock(blocks.StreamBlock):
    responsible_party = ResponsiblePartyFilterBlock()
    primary_org = PrimaryOrganizationFilterBlock()
    implementation_phase = ActionImplementationPhaseFilterBlock()
    schedule = ActionScheduleFilterBlock()
    attribute = ActionAttributeTypeFilterBlock()
    category = CategoryTypeFilterBlock()


class ActionListContentBlock(blocks.StaticBlock):
    block_label: str

    def get_admin_text(self):
        return _("Content block: %(label)s") % dict(label=self.label)


def get_field_label(model: Type[models.Model], field_name: str) -> str | None:
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


def generate_blocks_for_fields(model: Type[models.Model], fields: list[str | Tuple[str, dict]]):
    out = {}
    for field_name in fields:
        if isinstance(field_name, tuple):
            field_name, params = field_name
        else:
            params = {}

        camel_field = underscore_to_camelcase(field_name)
        class_name = '%s%sBlock' % (model._meta.object_name, camel_field)

        # Fields need to be evaluated lazily, because when this function is called,
        # the model registry is not yet fully initialized.
        field_label = lazy_field_label(model, field_name)
        Meta = type('Meta', (), {'label': params.get('label', field_label)})
        klass = type(class_name, (ActionListContentBlock,), {
            'Meta': Meta,
            '__module__': __name__,
        })
        register_streamfield_block(klass)
        globals()[class_name] = klass
        out[field_name] = klass
    return out


def generate_stream_block(
    name: str, all_blocks: dict[str, Type[blocks.Block]], fields: list[str | Tuple[str, blocks.Block]],
):
    field_blocks = {}
    for field in fields:
        if isinstance(field, tuple):
            field_name, block = field
            field_blocks[field_name] = block
        else:
            field_blocks[field] = all_blocks[field]()

    block = type(name, (blocks.StreamBlock,), {
        '__module__': __name__,
        **field_blocks,
    })

    return register_streamfield_block(block)


action_attribute_blocks = generate_blocks_for_fields(Action, [
    'lead_paragraph',
    'description',
    'official_name',
    'schedule',
    'links',
    'tasks',
    ('merged_actions', dict(label=_('Merged actions'))),
    'related_actions',
    'related_indicators',
    'contact_persons',
    'responsible_parties',
])


ActionMainContentBlock = generate_stream_block(
    'ActionMainContentBlock',
    action_attribute_blocks,
    fields=[
        'lead_paragraph',
        'description',
        'official_name',
        ('attribute', ActionAttributeTypeChooserBlock(required=True, label=_('Attribute'))),
        ('categories', CategoryTypeChooserBlock(required=True, label=_('Category'))),
        'links',
        'tasks',
        'merged_actions',
        'related_actions',
        'related_indicators',
    ],
)

ActionAsideContentBlock = generate_stream_block(
    'ActionAsideContentBlock',
    action_attribute_blocks,
    fields=[
        'schedule',
        'contact_persons',
        'responsible_parties',
        ('attribute', ActionAttributeTypeChooserBlock(required=True, label=_('Attribute'))),
        ('categories', CategoryTypeChooserBlock(required=True, label=_('Category'))),
    ],
)


def get_default_action_content_blocks(plan: Plan):
    action_ats: AttributeTypeQuerySet = AttributeType.objects.for_actions(plan)
    action_cts = CategoryType.objects.filter(plan=plan, usable_for_actions=True)

    main_blocks_top = [
        {'type': 'lead_paragraph', 'value': None},
        {'type': 'description', 'value': None},
        {'type': 'official_name', 'value': None},
        {'type': 'links', 'value': None},
        {'type': 'merged_actions', 'value': None},
        *[{'type': 'attribute', 'value': atype.id} for atype in action_ats],
        {'type': 'tasks', 'value': None},
    ]
    aside_blocks = [
        {'type': 'schedule', 'value': None},
        {'type': 'responsible_party', 'value': None},
        *[{'type': 'categories', 'value': ct.id} for ct in action_cts],
        {'type': 'contact_persons', 'value': None},
    ]
    main_blocks_bottom = [
        {'type': 'related_actions', 'value': None},
        {'type': 'related_indicators', 'value': None},
    ]
    blocks = [
        ('details_main_top', ActionMainContentBlock, main_blocks_top),
        ('details_aside', ActionAsideContentBlock, aside_blocks),
        ('details_main_bottom', ActionMainContentBlock, main_blocks_bottom),
    ]
    out = {}
    for field_name, kls, data in blocks:
        blk = kls()
        val = blk.clean(blk.to_python(data))
        out[field_name] = val
    return out


def get_default_action_filter_blocks(plan: Plan):
    filter_blocks = [
        {'type': 'responsible_party', 'value': None},
        {'type': 'implementation_phase', 'value': None},
        {'type': 'schedule', 'value': None},
    ]

    ignore_cts = []
    out = {}
    if plan.secondary_action_classification is not None:
        ct = plan.secondary_action_classification
        f = {'type': 'category', 'value': {'style': 'buttons', 'category_type': ct.id}}
        blk = ActionListFilterBlock()
        out['primary_filters'] = blk.clean(blk.to_python([f]))
        ignore_cts.append(ct)

    if plan.primary_action_classification is not None:
        ct = plan.primary_action_classification
        f = {'type': 'category', 'value': {'style': 'dropdown', 'category_type': ct.id}}
        filter_blocks.append(f)
        ignore_cts.append(ct)

    action_cts = CategoryType.objects.filter(plan=plan, usable_for_actions=True)
    for ct in action_cts:
        if ct in ignore_cts:
            continue
        f = {'type': 'category', 'value': {'style': 'dropdown', 'category_type': ct.id}}
        filter_blocks.append(f)

    action_ats: AttributeTypeQuerySet = AttributeType.objects.for_actions(plan)
    for atype in action_ats:
        if atype.format not in (atype.AttributeFormat.ORDERED_CHOICE, atype.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT):
            continue
        f = {'type': 'attribute', 'value': {'attribute_type': atype.id}}
        filter_blocks.append(f)

    blk = ActionListFilterBlock()
    out['main_filters'] = blk.clean(blk.to_python(filter_blocks))
    return out
