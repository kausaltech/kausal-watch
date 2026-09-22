"""
Regression tests for category icons assigned to a regional locale.

Icon rows store the language code as it appears in `settings.LANGUAGES`, which
spells regions in upper case (`es-US`, `sv-FI`). GraphQL resolvers look icons up
with `get_language()`, which Django always lower-cases, so an exact match never
found those rows and the icon silently resolved to `None`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from actions.tests.factories import (
    CategoryFactory,
    CategoryIconFactory,
    CategoryTypeFactory,
    CommonCategoryIconFactory,
    PlanFactory,
)
from images.tests.factories import AplansImageFactory

if TYPE_CHECKING:
    from images.models import AplansImage

pytestmark = pytest.mark.django_db

CATEGORY_ICON_QUERY = """
    query($plan: ID!, $lang: String!) @locale(lang: $lang) {
      planCategories(plan: $plan) {
        id
        iconImage {
          id
        }
      }
    }
"""


@pytest.fixture
def plan():
    return PlanFactory(primary_language='en', other_languages=['es-US'])


@pytest.fixture
def category(plan):
    return CategoryFactory(type=CategoryTypeFactory(plan=plan))


@pytest.mark.parametrize('requested_language', ['es-US', 'es-us'])
def test_get_icon_finds_icon_stored_under_regional_locale(category, requested_language):
    icon = CategoryIconFactory(category=category, language='es-US')

    assert category.get_icon(requested_language) == icon


def test_get_icon_does_not_confuse_region_with_base_language(category):
    base = CategoryIconFactory(category=category, language='es')
    regional = CategoryIconFactory(category=category, language='es-US')

    assert category.get_icon('es-us') == regional
    assert category.get_icon('es') == base


def test_get_icon_still_falls_back_when_the_regional_locale_has_no_icon(category):
    languageless = CategoryIconFactory(category=category, language=None)

    assert category.get_icon('es-us') == languageless


def test_common_category_icon_is_also_found_under_a_regional_locale(category):
    """The category has no icons of its own, so the lookup falls through to the common category."""
    icon = CommonCategoryIconFactory(common_category=category.common, language='es-US')

    assert category.get_icon('es-us') == icon


def test_category_icon_is_resolved_for_a_regional_locale(graphql_client_query_data, plan, category):
    image: AplansImage = AplansImageFactory()
    CategoryIconFactory(category=category, language='es-US', image=image)

    data = graphql_client_query_data(
        CATEGORY_ICON_QUERY,
        variables={'plan': plan.identifier, 'lang': 'es-US'},
    )

    [resolved] = [c for c in data['planCategories'] if c['id'] == str(category.id)]
    assert resolved['iconImage'] == {'id': str(image.id)}
