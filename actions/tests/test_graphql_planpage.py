import pytest

from actions.tests.factories import ActionListBlockFactory
from pages.models import CategoryPage
from pages.tests.factories import CardListBlockFactory, QuestionAnswerBlockFactory

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


@pytest.mark.django_db
def test_front_page_hero_block(graphql_client_query_data, plan, front_page_hero_block):
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


@pytest.mark.django_db
def test_category_list_block(graphql_client_query_data, plan, category_list_block):
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


@pytest.mark.django_db
def test_indicator_group_block(graphql_client_query_data, plan, indicator_block):
    indicator = indicator_block['indicator']
    assert not indicator.goals.exists()
    assert not indicator.levels.exists()
    assert indicator.latest_value is None
    unit = indicator.unit

    page = plan.root_page
    page.body = [
        ('indicator_group', [indicator_block]),
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
                    'minValue': None,
                    'maxValue': None,
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


@pytest.mark.django_db
def test_indicator_highlights_block(graphql_client_query_data, plan):
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


@pytest.mark.django_db
def test_indicator_showcase_block(graphql_client_query_data, plan, indicator_showcase_block):
    page = plan.root_page
    page.body = [
        ('indicator_showcase', indicator_showcase_block),
    ]
    page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan,
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


@pytest.mark.django_db
def test_action_highlights_block(graphql_client_query_data, plan):
    page = plan.root_page
    page.body = [
        ('action_highlights', None),
    ]
    page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan,
        block_fields='''
            __typename
        ''',
        expected={
            '__typename': 'ActionHighlightsBlock'
        }
    )


@pytest.mark.django_db
def test_card_list_block(graphql_client_query_data, plan, card_block):
    # NOTE: Due to a presumed bug in wagtail-factories, we deliberately do not register factories containing a
    # ListBlockFactory. For these factories, we *should not use a fixture* but instead use the factory explicitly.
    # https://github.com/wagtail/wagtail-factories/issues/40
    card_list_block = CardListBlockFactory(cards=[card_block])
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


@pytest.mark.django_db
def test_question_answer_block(graphql_client_query_data, plan, static_page, question_block):
    question_answer_block = QuestionAnswerBlockFactory(questions=[question_block])
    static_page.body = [
        ('qa_section', question_answer_block),
    ]
    static_page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan,
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


@pytest.mark.django_db
def test_static_page_lead_paragraph(graphql_client_query_data, plan, static_page):
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
            'plan': plan.identifier,
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


@pytest.mark.django_db
def test_static_page_header_image(graphql_client_query_data, plan, static_page):
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
            'plan': plan.identifier,
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


@pytest.mark.django_db
def test_static_page_body(graphql_client_query_data, plan, static_page):
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
            'plan': plan.identifier,
            'path': static_page.url_path,
        }
    )
    expected = {
        'planPage': {
            'body': [{
                'id': static_page.body[0].id,
                'blockType': 'CharBlock',
                'field': 'heading',
                'value': static_page.body[0].value,
            }, {
                'id': static_page.body[1].id,
                'blockType': 'RichTextBlock',
                'field': 'paragraph',
                # FIXME: The newline is added by grapple in RichTextBlock.resolve_value()
                'value': f'{static_page.body[1].value}\n',
            }, {
                'id': static_page.body[2].id,
                'blockType': 'QuestionAnswerBlock',
                'field': 'qa_section',
            }],
        }
    }
    assert data == expected


@pytest.mark.django_db
def test_categorymetadata_order_as_in_categorytypemetadata(
    graphql_client_query_data, plan, category, category_type, category_type_metadata_factory,
    category_metadata_rich_text_factory
):
    ctm0 = category_type_metadata_factory(type=category_type)
    ctm1 = category_type_metadata_factory(type=category_type)
    assert ctm0.order < ctm1.order
    cmrt0 = category_metadata_rich_text_factory(metadata=ctm0, category=category)
    cmrt1 = category_metadata_rich_text_factory(metadata=ctm1, category=category)
    category_page = CategoryPage(title='Category', slug='category-slug', category=category)
    plan.root_page.add_child(instance=category_page)

    query = '''
        query($plan: ID!, $path: String!) {
          planPage(plan: $plan, path: $path) {
            ... on CategoryPage {
              category {
                metadata {
                  ... on CategoryMetadataRichText {
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
        'plan': category_page.category.type.plan.identifier,
        'path': f'/{category.identifier}-category-slug',
    }
    expected = {
        'planPage': {
            'category': {
                'metadata': [{
                    'keyIdentifier': ctm0.identifier,
                    'value': cmrt0.text,
                }, {
                    'keyIdentifier': ctm1.identifier,
                    'value': cmrt1.text,
                }],
            }
        }
    }
    data = graphql_client_query_data(query, variables=query_variables)
    assert data == expected

    ctm0.order, ctm1.order = ctm1.order, ctm0.order
    ctm0.save()
    ctm1.save()
    expected_metadata = expected['planPage']['category']['metadata']
    expected_metadata[0], expected_metadata[1] = expected_metadata[1], expected_metadata[0]
    data = graphql_client_query_data(query, variables=query_variables)
    assert data == expected


@pytest.mark.django_db
def test_category_page_action_list(graphql_client_query_data, plan, category):
    category_page = CategoryPage(title='Category', slug='category-slug', category=category)
    plan.root_page.add_child(instance=category_page)
    action_list_block = ActionListBlockFactory(category_filter=category)
    category_page.body = [
        ('action_list', action_list_block),
    ]
    category_page.save()
    assert_body_block(
        graphql_client_query_data,
        plan=plan,
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