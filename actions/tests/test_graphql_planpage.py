import pytest
from wagtail import blocks

from actions.tests.factories import ActionListBlockFactory
from indicators.blocks import IndicatorBlock
from pages.blocks import CardBlock, QuestionBlock
from pages.tests.factories import CardListBlockFactory, QuestionAnswerBlockFactory

pytestmark = pytest.mark.django_db

MULTI_USE_IMAGE_FRAGMENT = '''
    fragment MultiUseImageFragment on Image {
      title
      width
      height
      focalPointX
      focalPointY
      rendition(size:"300x200") {
        width
        height
        src
      }
    }
    '''


def assert_body_block(graphql_client_query_data, plan, block_fields, expected, extra_fragments=None, page=None):
    if extra_fragments is None:
        extra_fragments_str = ''
    else:
        extra_fragments_str = '\n'.join(extra_fragments)

    if page is None:
        page = plan.root_page

    assert len(page.body) == 1
    block_type = type(page.body[0].block).__name__
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $path: String!) {
          planPage(plan: $plan, path: $path) {
            ... on %(page_type)s {
              body {
                id
                blockType
                field
                ...Block
              }
            }
          }
        }
        fragment Block on StreamFieldInterface {
          ... on %(block_type)s {
            %(block_fields)s
          }
        }
        %(extra_fragments)s
        ''' % {'page_type': type(page).__name__,
               'block_type': block_type,
               'block_fields': block_fields,
               'extra_fragments': extra_fragments_str},
        variables={
            'plan': plan.identifier,
            'path': page.url_path,
        }
    )
    expected = {
        'id': page.body[0].id,
        'blockType': block_type,
        'field': page.body[0].block.name,
        **expected
    }
    assert data == {'planPage': {'body': [expected]}}


def expected_result_multi_use_image_fragment(image_block):
    return {
        'title': image_block.title,
        'focalPointX': None,
        'focalPointY': None,
        'width': image_block.width,
        'height': image_block.height,
        'rendition': {
            'width': image_block.get_rendition('fill-300x200-c50').width,
            'height': image_block.get_rendition('fill-300x200-c50').height,
            'src': ('http://testserver' + image_block.get_rendition('fill-300x200-c50').url),
        },
    }


def test_front_page_hero_block(graphql_client_query_data, front_page_hero_block, plan_with_pages):
    plan = plan_with_pages
    page = plan.root_page
    page.body = [
        ('front_page_hero', front_page_hero_block),
    ]
    page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan,
        page=page,
        block_fields='''
            id
            layout
            image {
              ...MultiUseImageFragment
            }
            heading
            lead
        ''',
        extra_fragments=[MULTI_USE_IMAGE_FRAGMENT],
        expected={
            'heading': front_page_hero_block['heading'],
            'image': expected_result_multi_use_image_fragment(front_page_hero_block['image']),
            'layout': 'big_image',
            'lead': str(front_page_hero_block['lead']),
        }
    )


def test_category_list_block(graphql_client_query_data, category_list_block, plan_with_pages):
    plan = plan_with_pages
    page = plan.root_page
    page.body = [
        ('category_list', category_list_block),
    ]
    page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan,
        block_fields='''
            heading
            lead
            style
        ''',
        expected={
            'heading': category_list_block['heading'],
            'lead': str(category_list_block['lead']),
            'style': category_list_block['style'],
        }
    )


def test_indicator_group_block(graphql_client_query_data, indicator_block, plan_with_pages):
    plan = plan_with_pages
    indicator = indicator_block['indicator']
    assert not indicator.goals.exists()
    assert not indicator.levels.exists()
    assert indicator.latest_value is None
    unit = indicator.unit

    page = plan.root_page
    indicator_group = blocks.list_block.ListValue(blocks.list_block.ListBlock(IndicatorBlock), [indicator_block])
    page.body = [
        ('indicator_group', indicator_group),
    ]
    page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan,
        block_fields='''
            items {
              ... on IndicatorBlock {
                style
                indicator {
                  id
                  identifier
                  name
                  unit {
                    id
                    shortName
                    name
                  }
                  minValue
                  maxValue
                  description
                  timeResolution
                  latestValue {
                    id
                    date
                    value
                  }
                  goals {
                    id
                    date
                    value
                  }
                  level(plan: $plan)
                }
              }
            }
        ''',
        expected={
            'items': [{
                'style': 'graph',
                'indicator': {
                    'id': str(indicator.id),
                    'identifier': indicator.identifier,
                    'name': indicator.name,
                    'unit': {
                        'id': str(unit.id),
                        'shortName': unit.short_name,
                        'name': unit.name,
                    },
                    'minValue': indicator.min_value,
                    'maxValue': indicator.max_value,
                    'description': indicator.description,
                    # graphene_django puts choices into upper case in converter.convert_choice_name()
                    'timeResolution': indicator.time_resolution.upper(),
                    'latestValue': None,
                    'goals': [],
                    'level': None,
                },
            }]
        }
    )


def test_indicator_highlights_block(graphql_client_query_data, plan_with_pages):
    plan = plan_with_pages
    page = plan.root_page
    page.body = [
        ('indicator_highlights', None),
    ]
    page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan,
        block_fields='''
            __typename
        ''',
        expected={
            '__typename': 'IndicatorHighlightsBlock'
        }
    )


def test_indicator_showcase_block(graphql_client_query_data, plan_with_pages, indicator_showcase_block):
    page = plan_with_pages.root_page
    page.body = [
        ('indicator_showcase', indicator_showcase_block),
    ]
    page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan_with_pages,
        block_fields='''
            title
            body
            indicator {
              id
            }
        ''',
        expected={
            'title': indicator_showcase_block['title'],
            'body': str(indicator_showcase_block['body']),
            'indicator': {'id': str(indicator_showcase_block['indicator'].id)},
        }
    )


def test_action_highlights_block(plan_with_pages, graphql_client_query_data):
    page = plan_with_pages.root_page
    page.body = [
        ('action_highlights', None),
    ]
    page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan_with_pages,
        block_fields='''
            __typename
        ''',
        expected={
            '__typename': 'ActionHighlightsBlock'
        }
    )


def test_related_plan_list_block(graphql_client_query_data, plan_with_pages):
    plan = plan_with_pages
    page = plan.root_page
    page.body = [
        ('related_plans', None),
    ]
    page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan,
        block_fields='''
            __typename
        ''',
        expected={
            '__typename': 'RelatedPlanListBlock'
        }
    )


def test_card_list_block(graphql_client_query_data, card_block, plan_with_pages):
    plan = plan_with_pages
    # NOTE: Due to a presumed bug in wagtail-factories, we deliberately do not register factories containing a
    # ListBlockFactory. For these factories, we *should not use a fixture* but instead use the factory explicitly.
    # https://github.com/wagtail/wagtail-factories/issues/40
    cards = blocks.list_block.ListValue(blocks.list_block.ListBlock(CardBlock), [card_block])
    card_list_block = CardListBlockFactory(cards=cards)
    page = plan.root_page
    page.body = [
        ('cards', card_list_block),
    ]
    page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan,
        block_fields='''
            heading
            lead
            cards {
              ... on CardBlock {
                image {
                  ...MultiUseImageFragment
                }
                heading
                content
                link
              }
            }
        ''',
        extra_fragments=[MULTI_USE_IMAGE_FRAGMENT],
        expected={
            'heading': card_list_block['heading'],
            'lead': card_list_block['lead'],
            'cards': [{
                'image': expected_result_multi_use_image_fragment(card_block['image']),
                'heading': card_block['heading'],
                'content': card_block['content'],
                'link': card_block['link'],
            }],
        }
    )


def test_question_answer_block(graphql_client_query_data, plan_with_pages, static_page, question_block):
    questions = blocks.list_block.ListValue(blocks.list_block.ListBlock(QuestionBlock), [question_block])
    question_answer_block = QuestionAnswerBlockFactory(questions=questions)
    static_page.body = [
        ('qa_section', question_answer_block),
    ]
    static_page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan_with_pages,
        page=static_page,
        block_fields='''
            heading
            questions {
              ... on QuestionBlock {
                question
                answer
              }
            }
        ''',
        expected={
            'heading': question_answer_block['heading'],
            'questions': [{
                'question': question_block['question'],
                'answer': str(question_block['answer']),
            }],
        }
    )


def test_static_page_lead_paragraph(graphql_client_query_data, plan_with_pages, static_page):
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $path: String!) {
          planPage(plan: $plan, path: $path) {
            id
            slug
            title
            ... on StaticPage {
              leadParagraph
            }
          }
        }
        ''',
        variables={
            'plan': plan_with_pages.identifier,
            'path': static_page.url_path,
        }
    )
    expected = {
        'planPage': {
            'id': str(static_page.id),
            'slug': static_page.slug,
            'title': static_page.title,
            'leadParagraph': static_page.lead_paragraph,
        }
    }
    assert data == expected


def test_static_page_header_image(graphql_client_query_data, plan_with_pages, static_page):
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $path: String!) {
          planPage(plan: $plan, path: $path) {
            ... on StaticPage {
              headerImage {
                ...MultiUseImageFragment
              }
            }
          }
        }
        ''' + MULTI_USE_IMAGE_FRAGMENT,
        variables={
            'plan': plan_with_pages.identifier,
            'path': static_page.url_path,
        }
    )
    expected = {
        'planPage': {
            'headerImage': {
                'title': static_page.header_image.title,
                'focalPointX': None,
                'focalPointY': None,
                'width': static_page.header_image.width,
                'height': static_page.header_image.height,
                'rendition': {
                    'width': static_page.header_image.get_rendition('fill-300x200-c50').width,
                    'height': static_page.header_image.get_rendition('fill-300x200-c50').height,
                    'src': 'http://testserver' + static_page.header_image.get_rendition('fill-300x200-c50').url,
                },
            },
        }
    }
    assert data == expected


def test_static_page_body(graphql_client_query_data, plan_with_pages, static_page):
    # We omit checking non-primitive blocks as they get their own tests.
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $path: String!) {
          planPage(plan: $plan, path: $path) {
            ... on StaticPage {
              body {
                id
                blockType
                field
                ... on CharBlock {
                  value
                }
                ... on RichTextBlock {
                  value
                }
              }
            }
          }
        }
        ''',
        variables={
            'plan': plan_with_pages.identifier,
            'path': static_page.url_path,
        }
    )
    expected = {
        'planPage': {
            'body': [{
                'id': static_page.body[0].id,
                'blockType': 'RichTextBlock',
                'field': 'paragraph',
                'value': str(static_page.body[0].value),
            }, {
                'id': static_page.body[1].id,
                'blockType': 'QuestionAnswerBlock',
                'field': 'qa_section',
            }],
        }
    }
    assert data == expected


def test_attribute_category_choices_are_resolved_correctly(
    graphql_client_query_data, plan_with_pages, category_factory, category_page, category_type_factory, attribute_type_factory,
    attribute_category_choice_factory
):
    category_type_host = category_page.category.type
    category_host = category_page.category
    category_type_for_attribute = category_type_factory()
    categories = [category_factory(type=category_type_for_attribute) for c in range(0, 5)]
    at0 = attribute_type_factory(scope=category_type_host)
    acc0 = attribute_category_choice_factory(type=at0, content_object=category_host, categories=categories)

    query = '''
        query($plan: ID!, $path: String!) {
          planPage(plan: $plan, path: $path) {
            ... on CategoryPage {
              category {
                attributes {
                  ... on AttributeCategoryChoice {
                    keyIdentifier
                    categories {
                      id
                    }
                  }
                }
              }
            }
          }
        }
        '''
    query_variables = {
        'plan': plan_with_pages.identifier,
        'path': category_page.url_path,
    }
    expected = {
        'planPage': {
            'category': {
                'attributes': [{
                    'keyIdentifier': at0.identifier,
                    'categories': [{'id': str(c.id)} for c in acc0.categories.all()]
                }],
            }
        }
    }
    data = graphql_client_query_data(query, variables=query_variables)
    assert data == expected


def test_attribute_order_as_in_attribute_type(
    graphql_client_query_data, plan_with_pages, category, category_page, category_type, attribute_type_factory,
    attribute_rich_text_factory
):
    at0 = attribute_type_factory(scope=category_type)
    at1 = attribute_type_factory(scope=category_type)
    assert at0.order < at1.order
    art0 = attribute_rich_text_factory(type=at0, content_object=category)
    art1 = attribute_rich_text_factory(type=at1, content_object=category)

    query = '''
        query($plan: ID!, $path: String!) {
          planPage(plan: $plan, path: $path) {
            ... on CategoryPage {
              category {
                attributes {
                  ... on AttributeRichText {
                    keyIdentifier
                    value
                  }
                }
              }
            }
          }
        }
        '''
    query_variables = {
        'plan': plan_with_pages.identifier,
        'path': category_page.url_path,
    }
    expected = {
        'planPage': {
            'category': {
                'attributes': [{
                    'keyIdentifier': at0.identifier,
                    'value': art0.text,
                }, {
                    'keyIdentifier': at1.identifier,
                    'value': art1.text,
                }],
            }
        }
    }
    data = graphql_client_query_data(query, variables=query_variables)
    assert data == expected

    at0.order, at1.order = at1.order, at0.order
    at0.save()
    at1.save()
    expected_attributes = expected['planPage']['category']['attributes']
    expected_attributes[0], expected_attributes[1] = expected_attributes[1], expected_attributes[0]
    data = graphql_client_query_data(query, variables=query_variables)
    assert data == expected


def test_category_page_action_list(graphql_client_query_data, plan_with_pages, category, category_page):
    action_list_block = ActionListBlockFactory(category_filter=category)
    category_page.body = [
        ('action_list', action_list_block),
    ]
    category_page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan_with_pages,
        page=category_page,
        block_fields='''
            categoryFilter {
              id
            }
        ''',
        expected={
            'categoryFilter': {
                'id': str(category.id),
            },
        }
    )
