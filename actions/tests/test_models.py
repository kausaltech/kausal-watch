import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from actions.models import Action, Category, CategoryType


@pytest.mark.django_db
def test_plan_can_be_saved(plan):
    pass


@pytest.mark.django_db
def test_action_can_be_saved(action):
    pass


@pytest.mark.django_db
def test_action_no_duplicate_identifier_per_plan(plan):
    Action.objects.create(plan=plan, name='Test action 1', identifier='id')
    with pytest.raises(IntegrityError):
        Action.objects.create(plan=plan, name='Test action 2', identifier='id')


@pytest.mark.django_db
@pytest.mark.parametrize('color', ['invalid', '#fffffg', '#00'])
def test_category_color_invalid(category, color):
    category.color = color
    with pytest.raises(ValidationError):
        category.full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize('color', ['#ffFFff', '#000', 'red', 'rgb(1,2,3)', 'rgba(0%, 100%, 100%, 0.5)'])
def test_category_color_valid(category, color):
    category.color = color
    category.full_clean()
