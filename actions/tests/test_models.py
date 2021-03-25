import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from actions.models import Action
from actions.tests.factories import ActionFactory, CategoryFactory

pytestmark = pytest.mark.django_db


def test_plan_can_be_saved(plan):
    pass


def test_action_can_be_saved():
    ActionFactory()


def test_action_no_duplicate_identifier_per_plan(plan):
    Action.objects.create(plan=plan, name='Test action 1', identifier='id')
    with pytest.raises(IntegrityError):
        Action.objects.create(plan=plan, name='Test action 2', identifier='id')


@pytest.mark.parametrize('color', ['invalid', '#fffffg', '#00'])
def test_category_color_invalid(color):
    category = CategoryFactory()
    category.color = color
    with pytest.raises(ValidationError):
        category.full_clean()


@pytest.mark.parametrize('color', ['#ffFFff', '#000', 'red', 'rgb(1,2,3)', 'rgba(0%, 100%, 100%, 0.5)'])
def test_category_color_valid(color):
    category = CategoryFactory()
    category.color = color
    category.full_clean()
