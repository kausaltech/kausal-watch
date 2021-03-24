from factory import Factory, LazyAttribute, SelfAttribute, SubFactory
from wagtail_factories import (
    CharBlockFactory, ImageChooserBlockFactory, ListBlockFactory, PageFactory, StreamFieldFactory, StructBlockFactory
)
from wagtail_factories.blocks import BlockFactory
from wagtail.core.blocks import PageChooserBlock, RichTextBlock
from wagtail.core.rich_text import RichText

import pages
from images.tests.factories import AplansImageFactory


class PageChooserBlockFactory(BlockFactory):
    class Meta:
        model = PageChooserBlock

    value = SubFactory('pages.tests.factories.StaticPageFactory')


# wagtail-factories doesn't support rich text blocks.
# Copied from https://github.com/wagtail/wagtail-factories/pull/25
class RichTextBlockFactory(Factory):
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

    question = "What is your quest?"
    answer = RichText("<p>To seek the holy grail.</p>")


class QuestionAnswerBlockFactory(StructBlockFactory):
    class Meta:
        model = pages.blocks.QuestionAnswerBlock

    heading = "QA block heading"
    questions = ListBlockFactory(QuestionBlockFactory)


class FrontPageHeroBlockFactory(StructBlockFactory):
    class Meta:
        model = pages.blocks.FrontPageHeroBlock

    layout = 'big_image'
    image = SubFactory(ImageChooserBlockFactory)
    heading = "Front page hero block heading"
    lead = RichText("<p>Front page hero block lead</p>")


class PageLinkBlockFactory(StructBlockFactory):
    class Meta:
        model = pages.blocks.PageLinkBlock

    text = "Page link block text"
    page = SubFactory(PageChooserBlockFactory)


class StaticPageFactory(PageFactory):
    class Meta:
        model = pages.models.StaticPage

    header_image = SubFactory(AplansImageFactory)
    lead_paragraph = "Lead paragraph"
    # body = [
    #     ('heading', "Heading"),
    #     ('paragraph', "<p>Paragraph</p>"),
    #     ('qa_section', {
    #         'heading': "QA section heading",
    #         'questions': [{
    #             'question': "Question",
    #             'answer': "Answer",
    #         }]
    #     }),
    # ]
    body = StreamFieldFactory({
        'heading': CharBlockFactory,
        'paragraph': RichTextBlockFactory,
        'qa_section': QuestionAnswerBlockFactory,
    })
    body__0__heading__value = "Test heading"
    body__1__paragraph__value = "<p>Test paragraph</p>"
    body__2__qa_section__heading = "QA section heading"
    body__2__qa_section__questions__0 = None


class CategoryPageFactory(PageFactory):
    class Meta:
        model = pages.models.CategoryPage

    title = LazyAttribute(lambda obj: f'Page for Category {obj.category.id}')
    category = SubFactory('actions.tests.factories.CategoryFactory', _category_page=None)
    body = StreamFieldFactory({
        'text': RichTextBlockFactory,
        # TODO: Write factories
        # 'indicator_group': IndicatorGroupBlockFactory,
        # 'category_list': CategoryListBlockFactory,
        # 'action_list': ActionListBlockFactory,
    })
    # TODO: Fill body
    # A category page must have a parent (assumed in CategoryPage.set_url_path)
    parent = SelfAttribute('category.type.plan.root_page')


class CardBlockFactory(StructBlockFactory):
    class Meta:
        model = pages.blocks.CardBlock

    image = SubFactory(ImageChooserBlockFactory)
    heading = "Card block heading"
    content = "Card block content"
    link = 'http://example.com'


class CardListBlockFactory(StructBlockFactory):
    class Meta:
        model = pages.blocks.CardListBlock

    heading = "Card list block heading"
    lead = "<p>Card list block lead</p>"
    cards = ListBlockFactory(CardBlockFactory)
