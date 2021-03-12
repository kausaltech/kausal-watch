import pytest

from pages.models import CategoryPage

MULTI_USE_IMAGE_FRAGMENT = '''
    fragment MultiUseImageFragment on Image {
      title
      width
      height
      focalPointX
      focalPointY
      large: rendition(size:"1600x600") {
        width
        height
        src
      }
      small: rendition(size:"600x300") {
        width
        height
        src
      }
      social: rendition(size:"1200x627") {
        width
        height
        src
      }
      rendition(size:"300x200") {
        width
        height
        src
      }
    }
    '''

STREAMFIELD_FRAGMENT = '''
    fragment StreamFieldFragment on StreamFieldInterface {
      id
      blockType
      field
      ... on CharBlock {
        value
      }
      ... on TextBlock {
        value
      }
      ... on RichTextBlock {
        value
      }
      ... on ChoiceBlock {
        value
        choices {
          key
          value
        }
      }
      ...on QuestionAnswerBlock {
        heading
        questions {
          ... on QuestionBlock {
            question
            answer
          }
        }
      }
      ... on IndicatorBlock {
        style
        indicator {
          id
        }
      }
      ... on IndicatorGroupBlock {
        id
        blockType
        rawValue
        items {
          ... on IndicatorBlock {
            id
            style
            indicator {
              id
              identifier
              name
              unit {
                id
                name
              }
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
      }
      ... on ActionListBlock {
        categoryFilter {
          id
        }
      }
      ... on CategoryListBlock {
        style
      }
      ... on FrontPageHeroBlock {
        id
        layout
        image {
          ...MultiUseImageFragment
        }
        heading
        lead
      }
      ... on IndicatorShowcaseBlock {
        id
        blockType
        field
        rawValue
        blocks {
          __typename
        }
        title
        body
        indicator {
          id
          identifier
          name
          unit {
            id
            shortName
          }
          minValue
          maxValue
          latestValue {
            date
            value
          }
          values {
            date
            value
          }
          goals {
            date
            value
          }
        }
        linkButton {
          blockType
          ... on PageLinkBlock {
            text
            page {
              url
              urlPath
              slug
            }
          }

        }
      }
      ... on CardListBlock {
        id
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
      }
      ... on ActionHighlightsBlock {
        field
      }
      ... on IndicatorHighlightsBlock {
        field
      }
    }
    '''


@pytest.mark.django_db
def test_planpage(graphql_client_query_data, plan):
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $path: String!) {
          planPage(plan: $plan, path: $path) {
            id
            slug
            title
          }
        }
        ''',
        variables={
            'plan': plan.identifier,
            'path': '/',
        }
    )
    expected = {
        'planPage': {
            'id': str(plan.root_page.id),
            'slug': plan.root_page.slug,
            'title': plan.root_page.title,
        }
    }
    assert data == expected


@pytest.mark.django_db
def test_static_page(graphql_client_query_data, plan, static_page):
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $path: String!) {
          planPage(plan: $plan, path: $path) {
            id
            slug
            title
            ... on StaticPage {
              headerImage {
                ...MultiUseImageFragment
              }
              leadParagraph
              body {
                ...StreamFieldFragment
              }
            }
          }
        }
        ''' + MULTI_USE_IMAGE_FRAGMENT + STREAMFIELD_FRAGMENT,
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
            'headerImage': None,  # TODO
            'leadParagraph': static_page.lead_paragraph,
            'body': [{
                'blockType': 'CharBlock',
                'field': 'heading',
                'id': static_page.body[0].id,
                'value': static_page.body[0].value,
            }, {
                'blockType': 'RichTextBlock',
                'field': 'paragraph',
                'id': static_page.body[1].id,
                # FIXME: The newline is added by grapple in RichTextBlock.resolve_value()
                'value': f'{static_page.body[1].value}\n',
            }, {
                'blockType': 'QuestionAnswerBlock',
                'field': 'qa_section',
                'heading': static_page.body[2].value['heading'],
                'id': static_page.body[2].id,
                'questions': [{
                    'question': static_page.body[2].value['questions'][0]['question'],
                    'answer': str(static_page.body[2].value['questions'][0]['answer']),
                }],
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
