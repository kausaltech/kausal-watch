from typing import Tuple, Type

from django.apps import apps
from django.db import models
from django.utils.functional import cached_property, lazy
from django.utils.translation import gettext_lazy as _
from wagtail.core import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLStreamfield, GraphQLString

from actions.models.action import Action
from actions.models.attributes import AttributeType, AttributeTypeQuerySet
from actions.models.category import CategoryType
from actions.models.plan import Plan
from aplans.utils import underscore_to_camelcase

from .chooser import AttributeTypeChooser, CategoryChooser, CategoryTypeChooser
from .models import Category


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
    mixins=None, extra_args=None
):
    if mixins is None:
        mixins = ()
    if extra_args is None:
        extra_args = {}
    field_blocks = {}
    graphql_types = list()
    for field in fields:
        if isinstance(field, tuple):
            field_name, block = field
            field_blocks[field_name] = block
        else:
            field_name = field
            block = all_blocks[field]()

        block_cls = type(block)
        if block_cls not in graphql_types:
            graphql_types.append(block_cls)
        field_blocks[field_name] = block

    block_class = type(name, (*mixins, blocks.StreamBlock), {
        '__module__': __name__,
        **field_blocks,
        **extra_args,
        'graphql_types': graphql_types
    })

    register_streamfield_block(block_class)
    return block_class


def get_default_action_content_blocks(plan: Plan):
    action_ats: AttributeTypeQuerySet = AttributeType.objects.for_actions(plan)
    action_cts = plan.category_types.filter(categories__actions__isnull=False, usable_for_actions=True).distinct()

    main_blocks_top = [
        {'type': 'lead_paragraph', 'value': None},
        {'type': 'description', 'value': None},
        {'type': 'official_name', 'value': None},
        {'type': 'links', 'value': None},
        {'type': 'merged_actions', 'value': None},
        *[{'type': 'attribute', 'value': dict(attribute_type=atype.id)} for atype in action_ats],
        {'type': 'tasks', 'value': None},
    ]
    aside_blocks = [
        {'type': 'schedule', 'value': None},
        {'type': 'responsible_parties', 'value': None},
        *[{'type': 'categories', 'value': dict(category_type=ct.id)} for ct in action_cts],
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
    filter_blocks: list[dict] = [
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

#
# Action List Filter blocks
#


@register_streamfield_block
class ActionAttributeTypeFilterBlock(blocks.StructBlock):
    attribute_type = ActionAttributeTypeChooserBlock(required=True, label=_("Attribute type"))
    show_all_label = blocks.CharBlock(required=False, label=_("Label for 'show all'"))

    model_instance_container_blocks = {
        AttributeType: 'attribute_type',
    }

    graphql_fields = [
        GraphQLString('show_all_label'),
        GraphQLForeignKey('attribute_type', AttributeType, required=True)
    ]

    class Meta:
        label = _("Attribute")


@register_streamfield_block
class CategoryTypeFilterBlock(blocks.StructBlock):
    style = blocks.ChoiceBlock(choices=[
        ('dropdown', _('Dropdown')),
        ('buttons', _('Buttons')),
    ], label=_("Style"), default='dropdown')
    show_all_label = blocks.CharBlock(required=False, label=_("Label for 'show all'"))
    category_type = CategoryTypeChooserBlock(required=True, label=_("Category type"))

    model_instance_container_blocks = {
        CategoryType: 'category_type',
    }

    graphql_fields = [
        GraphQLString('style'),
        GraphQLString('show_all_label'),
        GraphQLForeignKey('category_type', CategoryType)
    ]

    class Meta:
        label = _("Category")


class FilterBlock(blocks.StaticBlock):
    graphql_fields = []

    def get_admin_text(self):
        return _("Filter: %(filter_label)s") % dict(filter_label=self.meta.label)


@register_streamfield_block
class ResponsiblePartyFilterBlock(FilterBlock):
    class Meta:
        label = _("responsible party")


@register_streamfield_block
class PrimaryOrganizationFilterBlock(FilterBlock):
    class Meta:
        label = _("primary organization")


@register_streamfield_block
class ActionImplementationPhaseFilterBlock(FilterBlock):
    class Meta:
        label = _("implementation phase")


@register_streamfield_block
class ActionScheduleFilterBlock(FilterBlock):
    class Meta:
        label = _("schedule")


class ActionListPageBlockPresenceMixin:
    def contains_model_instance(self, instance, blocks):
        container_block_name = self.model_instance_container_blocks[instance._meta.model]
        container_blocks = (child for child in blocks if child.block_type == container_block_name)
        child_block_class = self.child_blocks[container_block_name]
        subblock_name = child_block_class.model_instance_container_blocks[instance._meta.model]
        for child in container_blocks:
            if child.value.get(subblock_name) == instance:
                return True
        return False

    def insert_model_instance(self, instance, blocks):
        block_name = self.model_instance_container_blocks[instance._meta.model]
        child_block = self.child_blocks[block_name]
        subblock_name = child_block.model_instance_container_blocks[instance._meta.model]
        blocks.append((block_name, {subblock_name: instance}))

    def remove_model_instance(self, instance, blocks):
        block_name = self.model_instance_container_blocks[instance._meta.model]
        child_block = self.child_blocks[block_name]
        subblock_name = child_block.model_instance_container_blocks[instance._meta.model]
        for i, block in enumerate(blocks):
            if (block.block_type == block_name and block.value[subblock_name] == instance):
                break
        else:
            raise ValueError(f"Model instance {instance} is not referenced in blocks")
        blocks.pop(i)


@register_streamfield_block
class ActionListFilterBlock(ActionListPageBlockPresenceMixin, blocks.StreamBlock):
    responsible_party = ResponsiblePartyFilterBlock()
    primary_org = PrimaryOrganizationFilterBlock()
    implementation_phase = ActionImplementationPhaseFilterBlock()
    schedule = ActionScheduleFilterBlock()
    attribute = ActionAttributeTypeFilterBlock()
    category = CategoryTypeFilterBlock()

    model_instance_container_blocks = {
        AttributeType: 'attribute',
        CategoryType: 'category',
    }

    graphql_types = [
        ResponsiblePartyFilterBlock, PrimaryOrganizationFilterBlock, ActionImplementationPhaseFilterBlock,
        ActionScheduleFilterBlock, ActionAttributeTypeFilterBlock, CategoryTypeFilterBlock
    ]

#
# Action Details / Content blocks
#


@register_streamfield_block
class ActionContentAttributeTypeBlock(blocks.StructBlock):
    attribute_type = ActionAttributeTypeChooserBlock(required=True)

    model_instance_container_blocks = {
        AttributeType: 'attribute_type',
    }

    graphql_fields = [
        GraphQLForeignKey('attribute_type', AttributeType, required=True)
    ]


@register_streamfield_block
class ActionContentCategoryTypeBlock(blocks.StructBlock):
    category_type = CategoryTypeChooserBlock(required=True)

    model_instance_container_blocks = {
        CategoryType: 'category_type',
    }

    graphql_fields = [
        GraphQLForeignKey('category_type', CategoryType, required=True)
    ]


@register_streamfield_block
class ActionOfficialNameBlock(blocks.StructBlock):
    field_label = blocks.CharBlock(
        required=False,
        help_text=_("What label should be used in the public UI for the official name"),
        default='',
    )
    caption = blocks.CharBlock(
        required=False, help_text=_("Description to show after the field content"), default='',
    )

    graphql_fields = [
        GraphQLString('field_label'),
        GraphQLString('caption'),
    ]

    def bulk_to_python(self, values):
        # Workaround for migration from StaticBlock to StructBlock
        li = list(values)
        if len(li) == 1 and li[0] is None:
            values = [{}]
        return super().bulk_to_python(values)


class ActionListContentBlock(blocks.StaticBlock):
    block_label: str

    def get_admin_text(self):
        return _("Content block: %(label)s") % dict(label=self.label)


action_attribute_blocks = generate_blocks_for_fields(Action, [
    'lead_paragraph',
    'description',
    'schedule',
    'links',
    'tasks',
    ('merged_actions', dict(label=_('Merged actions'))),
    'related_actions',
    'related_indicators',
    'contact_persons',
    'responsible_parties',
])


action_content_fields = [
    'lead_paragraph',
    'description',
    ('official_name', ActionOfficialNameBlock(label=_('official name'))),
    ('attribute', ActionContentAttributeTypeBlock(label=_('Attribute'))),
    ('categories', ActionContentCategoryTypeBlock(label=_('Category'))),
    'links',
    'tasks',
    'merged_actions',
    'related_actions',
    'related_indicators',
]

action_content_extra_args = {
    'model_instance_container_blocks': {
        AttributeType: 'attribute',
        CategoryType: 'categories',
    },
}

ActionContentSectionElementBlock = generate_stream_block(
    'ActionMainContentSectionElementBlock',
    action_attribute_blocks,
    fields=action_content_fields,
)


@register_streamfield_block
class ActionContentSectionBlock(blocks.StructBlock):
    layout = blocks.ChoiceBlock(choices=[
        ('full-width', _('Full width')),
        ('grid', _('Grid')),
    ])
    heading = blocks.CharBlock(classname='full title', label=_('Heading'), required=False)
    help_text = blocks.CharBlock(label=_('Help text'), required=False)
    blocks = ActionContentSectionElementBlock(label=_('Blocks'))

    graphql_fields = [
        GraphQLString('layout'),
        GraphQLString('heading'),
        GraphQLString('help_text'),
        GraphQLStreamfield('blocks'),
    ]


ActionMainContentBlock = generate_stream_block(
    'ActionMainContentBlock',
    action_attribute_blocks,
    fields=[
        ('section', ActionContentSectionBlock(required=True, label=_('Section'))),
        *action_content_fields,
    ],
    mixins=(ActionListPageBlockPresenceMixin,),
    extra_args={
        **action_content_extra_args,
    },
)

ActionAsideContentBlock = generate_stream_block(
    'ActionAsideContentBlock',
    action_attribute_blocks,
    fields=[
        'schedule',
        'contact_persons',
        'responsible_parties',
        ('attribute', ActionContentAttributeTypeBlock(required=True, label=_('Attribute'))),
        ('categories', ActionContentCategoryTypeBlock(required=True, label=_('Category'))),
    ],
    mixins=(ActionListPageBlockPresenceMixin,),
    extra_args={
        **action_content_extra_args,
    },
)


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
