from factory import Factory, SubFactory
from wagtail_factories import CharBlockFactory, ListBlockFactory, PageFactory, StreamFieldFactory, StructBlockFactory
from wagtail.core.blocks import RichTextBlock

import pages
from images.tests.factories import AplansImageFactory


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
    # answer = RichText("<p>To seek the holy grail.</p>")
    answer = SubFactory(RichTextBlockFactory)
    answer__value = "<p>To seek the holy grail.</p>"


class QuestionAnswerBlockFactory(StructBlockFactory):
    class Meta:
        model = pages.blocks.QuestionAnswerBlock

    heading = "QA block heading"
    questions = ListBlockFactory(QuestionBlockFactory)


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
