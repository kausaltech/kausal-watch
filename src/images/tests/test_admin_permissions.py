from django.test import RequestFactory
from wagtail.images import permissions
from wagtail.images.views.images import IndexView

import pytest

from actions.tests.factories import PlanFactory
from images.permissions import permission_policy
from images.tests.factories import AplansImageFactory
from users.tests.factories import UserFactory


def test_image_views_use_plan_permission_policy():
    from wagtail.images.views import images

    assert permissions.permission_policy is permission_policy
    assert images.permission_policy is permission_policy
    assert IndexView.permission_policy is permission_policy


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
