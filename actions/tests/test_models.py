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
def test_category_color_invalid(category):
    category.color = 'invalid'
    with pytest.raises(ValidationError):
        category.full_clean()
