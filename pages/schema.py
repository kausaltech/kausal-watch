import functools
import graphene

from graphene.types.generic import GenericScalar
from graphene_django.converter import convert_django_field
from wagtail.core.fields import StreamField as WagtailStreamField
from wagtail.core.blocks import field_block, StaticBlock as WagtailStaticBlock

from aplans.graphql_types import DjangoNode

from . import blocks as pages_blocks
from pages.models import AplansPage, StaticPage as WStaticPage, PlanRootPage


BASE_PAGE_FIELDS = [
    'id', 'slug', 'title', 'url_path',
]


class Page(graphene.Interface):
    id = graphene.ID(required=True)
    title = graphene.String(required=True)
    slug = graphene.String(required=True)
    url_path = graphene.String(required=True)
    parent = graphene.Field('pages.schema.Page')


class BasePageNode(DjangoNode):
    def resolve_parent(self, info):
        if isinstance(self, PlanRootPage):
            return None

        return self.get_parent()

    class Meta:
        abstract = True


class StreamFieldBlock(graphene.Interface):
    id = graphene.ID(required=True)
    name = graphene.String(required=True)

    @classmethod
    def resolve_type(cls, instance, info):
        if isinstance(instance.block, field_block.CharBlock):
            return CharBlock
        elif isinstance(instance.block, field_block.RichTextBlock):
            return RichTextBlock
        elif isinstance(instance.block, field_block.ChoiceBlock):
            return CharBlock
        elif isinstance(instance.block, WagtailStaticBlock):
            return StaticBlock
        elif isinstance(instance.block, pages_blocks.QuestionAnswerBlock):
            return QuestionAnswerBlock
        elif isinstance(instance.block, pages_blocks.FrontPageHeroBlock):
            return FrontPageHeroBlock
        else:
            raise Exception('Unknown type: %s' % instance.block)

    def resolve_name(self, info):
        return self.block.name


class RichTextBlock(graphene.ObjectType):
    value = graphene.String(required=True)

    def resolve_value(self, info):
        return str(self)

    class Meta:
        interfaces = (StreamFieldBlock,)


class StaticBlock(graphene.ObjectType):
    class Meta:
        interfaces = (StreamFieldBlock,)


class CharBlock(graphene.ObjectType):
    value = graphene.String(required=True)

    class Meta:
        interfaces = (StreamFieldBlock,)


class StructBlock(graphene.ObjectType):
    @classmethod
    def __init_subclass_with_meta__(cls, **kwargs):
        def resolve_field(field_name, obj, info):
            ret = obj.value[field_name]
            return ret

        kwargs['interfaces'] = (StreamFieldBlock,)
        super().__init_subclass_with_meta__(**kwargs)

        for field_name, field in cls._meta.fields.items():
            if field_name in ('id', 'name'):
                continue
            field.resolver = functools.partial(resolve_field, field_name)

    class Meta:
        # interfaces = (StreamFieldBlock,)
        abstract = True


class QuestionAnswer(graphene.ObjectType):
    question = graphene.String(required=True)
    answer = graphene.String(required=True)


class QuestionAnswerBlock(StructBlock):
    heading = graphene.String(required=True)
    questions = graphene.List(QuestionAnswer)


class FrontPageHeroBlock(StructBlock):
    layout = graphene.String(required=True)
    image = graphene.Field('images.schema.ImageNode')


class StreamField(graphene.ObjectType):
    blocks = graphene.List(StreamFieldBlock)

    def resolve_blocks(self, info):
        return list(self)


@convert_django_field.register(WagtailStreamField)
def convert_stream_field(field, registry=None):
    return graphene.Field(StreamField, description=field.help_text, required=not field.null)


class WStaticPageNode(BasePageNode):
    class Meta:
        model = WStaticPage
        only_fields = BASE_PAGE_FIELDS + ['header_image', 'lead_paragraph', 'body']
        interfaces = (Page,)


class RootPageNode(BasePageNode):
    class Meta:
        model = PlanRootPage
        only_fields = BASE_PAGE_FIELDS + ['body']
        interfaces = (Page,)


types = [
    WStaticPageNode, RootPageNode, CharBlock, StaticBlock, QuestionAnswerBlock, RichTextBlock, FrontPageHeroBlock,
]
