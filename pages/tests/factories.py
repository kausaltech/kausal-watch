from wagtail.blocks import PageChooserBlock, RichTextBlock
from wagtail.fields import StreamField
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Page
from wagtail.rich_text import RichText
from wagtail.test.utils.wagtail_factories import (
    CharBlockFactory,
    ImageChooserBlockFactory,
    ListBlockFactory,
    PageFactory,
    StreamBlockFactory,
    StreamFieldFactory,
    StructBlockFactory,
)
from wagtail.test.utils.wagtail_factories.blocks import BlockFactory

from factory import LazyAttribute, SelfAttribute, SubFactory

from aplans.factories import ModelFactory

import pages.blocks
import pages.models
from actions.blocks.category_page_layout import CategoryPageAttributeTypeBlock, CategoryPageProgressBlock
from actions.models import Category, CategoryLevel, CategoryType
from actions.tests.factories import CategoryLevelFactory, CategoryPageAttributeTypeBlockFactory, CategoryPageProgressBlockFactory
from images.models import AplansImage
from images.tests.factories import AplansImageFactory


class PageChooserBlockFactory(BlockFactory):
    class Meta:
        model = PageChooserBlock

    value = SubFactory[PageChooserBlock, pages.models.StaticPage]('pages.tests.factories.StaticPageFactory')


# wagtail-factories doesn't support rich text blocks.
# Copied from https://github.com/wagtail/wagtail-factories/pull/25
class RichTextBlockFactory(StreamBlockFactory):
    @classmethod
    def _build(cls, model_class, value=''):
        block = model_class()
        return block.to_python(value)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return cls._build(model_class, *args, **kwargs)

    class Meta:
        model = RichTextBlock


class QuestionBlockFactory(StructBlockFactory):
    class Meta:
        model = pages.blocks.QuestionBlock

    question = 'What is your quest?'
    answer = RichText('<p>To seek the holy grail.</p>')


class QuestionAnswerBlockFactory(StructBlockFactory):
    class Meta:
        model = pages.blocks.QuestionAnswerBlock

    heading = 'QA block heading'
    questions = ListBlockFactory(QuestionBlockFactory)


class FrontPageHeroAdditionalSettingsBlockFactory(StructBlockFactory):
    class Meta:
        model = pages.blocks.FrontPageHeroAdditionalSettingsBlock

    background_colour = ''
    fit_image = True


class FrontPageHeroBlockFactory(StructBlockFactory):
    class Meta:
        model = pages.blocks.FrontPageHeroBlock

    layout = 'big_image'
    image = SubFactory[pages.blocks.FrontPageHeroBlock, ImageChooserBlock](ImageChooserBlockFactory)
    heading = 'Front page hero block heading'
    lead = RichText('<p>Front page hero block lead</p>')
    additional_settings = SubFactory[pages.blocks.FrontPageHeroBlock, pages.blocks.FrontPageHeroAdditionalSettingsBlock](
        FrontPageHeroAdditionalSettingsBlockFactory
    )


class PageLinkBlockFactory(StructBlockFactory):
    class Meta:
        model = pages.blocks.PageLinkBlock

    text = 'Page link block text'
    page = SubFactory[pages.blocks.PageLinkBlock, PageChooserBlock](PageChooserBlockFactory)


class StaticPageFactory(PageFactory):
    class Meta:
        model = pages.models.StaticPage

    header_image = SubFactory[pages.models.StaticPage, AplansImage](AplansImageFactory)
    lead_paragraph = 'Lead paragraph'
    # Used to work but then got broken at some point
    # body = [
    #     ('paragraph', RichText("<p>Paragraph</p>")),
    #     ('qa_section', {
    #         'heading': "QA section heading",
    #         'questions': [{
    #             'question': "Question",
    #             'answer': RichText("<p>Answer</p>"),
    #         }]
    #     }),
    # ]
    body = StreamFieldFactory({
        'heading': SubFactory(CharBlockFactory),
        'paragraph': SubFactory(RichTextBlockFactory),
        'qa_section': SubFactory(QuestionAnswerBlockFactory),
    })
    body__0__paragraph = RichText('<p>Test paragraph</p>')
    body__1__qa_section__heading = 'QA section heading'
    body__1__qa_section__questions__0__question = 'Question'
    body__1__qa_section__questions__0__answer = RichText('<p>Answer<p>')


class CategoryPageFactory(PageFactory):
    class Meta:
        model = pages.models.CategoryPage

    title = LazyAttribute[pages.models.CategoryPage, str](lambda obj: f'Page for Category {obj.category.id}')
    category = SubFactory[pages.models.CategoryPage, Category]('actions.tests.factories.CategoryFactory', _category_page=None)
    # This was the old version and after a Wagtail upgrade the `qa_section` part in StaticPageFactory broke, but maybe
    # it works as done below? We tried to use it that way already some time ago anyway, but there seemed to be some
    # problem back then.
    # body = StreamFieldFactory({
    #     'text': RichTextBlockFactory,
    #     # TODO: Write factories
    #     # 'indicator_group': IndicatorGroupBlockFactory,
    #     # 'category_list': CategoryListBlockFactory,
    #     # 'action_list': ActionListBlockFactory,
    # })
    body = [
        ('text', RichText('<p>Hello</p>')),
    ]
    # A category page must have a parent (assumed in CategoryPage.set_url_path)
    parent = SelfAttribute[pages.models.CategoryPage, Page]('category.type.plan.root_page')


class CategoryTypePageFactory(StaticPageFactory):
    class Meta:
        model = pages.models.CategoryTypePage

    category_type = SubFactory[pages.models.CategoryTypePage, CategoryType]('actions.tests.factories.CategoryTypeFactory')


class CategoryTypePageLevelLayoutFactory(ModelFactory[pages.models.CategoryTypePageLevelLayout]):
    page = SubFactory[pages.models.CategoryTypePageLevelLayout, pages.models.CategoryTypePage](CategoryTypePageFactory)
    level = SubFactory[pages.models.CategoryTypePageLevelLayout, CategoryLevel](CategoryLevelFactory)
    layout_main_top = StreamFieldFactory({
        'attribute': SubFactory[StreamField, CategoryPageAttributeTypeBlock](CategoryPageAttributeTypeBlockFactory),
        'progress': SubFactory[StreamField, CategoryPageProgressBlock](CategoryPageProgressBlockFactory),
    })
    # If we wanted this factory to create an example layout:
    # layout_main_top__0__attribute__attribute_type__name = 'foo'
    # layout_main_top__1 = 'progress'


class CardBlockFactory(StructBlockFactory):
    class Meta:
        model = pages.blocks.CardBlock

    image = SubFactory[pages.blocks.CardBlock, ImageChooserBlock](ImageChooserBlockFactory)
    heading = 'Card block heading'
    content = 'Card block content'
    link = 'http://example.com'


class CardListBlockFactory(StructBlockFactory):
    class Meta:
        model = pages.blocks.CardListBlock

    heading = 'Card list block heading'
    lead = '<p>Card list block lead</p>'
    cards = ListBlockFactory(CardBlockFactory)
