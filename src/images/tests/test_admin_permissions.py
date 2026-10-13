from django.test import RequestFactory
from wagtail.images import get_image_model
from wagtail.images.views.images import IndexView
from wagtail.permissions import policy_registry

import pytest

from actions.tests.factories import CommonCategoryTypeFactory, PlanFactory
from images.permissions import permission_policy
from images.tests.factories import AplansImageFactory
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory


def test_image_permission_policy_is_registered():
    assert policy_registry.get_by_type(get_image_model()) is permission_policy


@pytest.mark.django_db
def test_image_index_queryset_tracks_active_plan():
    first_plan = PlanFactory.create()
    second_plan = PlanFactory.create()
    assert first_plan.root_collection is not None
    nested_collection = first_plan.root_collection.add_child(name='Nested images')
    first_image = AplansImageFactory.create(collection=first_plan.root_collection)
    nested_image = AplansImageFactory.create(collection=nested_collection)
    other_image = AplansImageFactory.create(collection=second_plan.root_collection)
    user = UserFactory.create(is_superuser=True, selected_admin_plan=first_plan)
    request = RequestFactory().get('/admin/images/')
    request.user = user
    view = IndexView()
    view.setup(request)
    view.needs_usage_count_subquery = False

    assert set(view.get_base_queryset().values_list('pk', flat=True)) == {first_image.pk, nested_image.pk}

    user.selected_admin_plan = second_plan
    user.save(update_fields=['selected_admin_plan'])
    # A subsequent request gets a fresh user and active-plan cache.
    request.user = type(user).objects.get(pk=user.pk)
    assert list(view.get_base_queryset().values_list('pk', flat=True)) == [other_image.pk]


@pytest.mark.django_db
def test_superuser_sees_common_category_type_images():
    plan = PlanFactory.create()
    cct = CommonCategoryTypeFactory.create(has_collection=True)
    assert cct.collection is not None
    plan_image = AplansImageFactory.create(collection=plan.root_collection)
    cct_image = AplansImageFactory.create(collection=cct.collection)
    superuser = UserFactory.create(is_superuser=True, selected_admin_plan=plan)
    plan_admin = PersonFactory.create(general_admin_plans=[plan]).user
    assert plan_admin is not None

    assert set(permission_policy.instances_user_has_any_permission_for(superuser, ['choose'])) == {plan_image, cct_image}
    assert cct_image not in permission_policy.instances_user_has_any_permission_for(plan_admin, ['choose'])
