from django.test import RequestFactory
from wagtail.documents import permissions
from wagtail.documents.views.documents import IndexView

import pytest

from actions.tests.factories import PlanFactory
from documents.permissions import permission_policy
from documents.tests.factories import AplansDocumentFactory
from users.tests.factories import UserFactory


def test_document_views_use_plan_permission_policy():
    from wagtail.documents.forms import BaseDocumentForm
    from wagtail.documents.views import chooser, documents

    from documents import chooser as custom_chooser

    assert chooser.permission_policy is permission_policy
    assert chooser.DocumentChooserViewSet.permission_policy is permission_policy
    assert chooser.viewset.permission_policy is permission_policy
    assert custom_chooser.permission_policy is permission_policy
    assert BaseDocumentForm.permission_policy is permission_policy
    assert permissions.permission_policy is permission_policy
    assert documents.permission_policy is permission_policy
    assert IndexView.permission_policy is permission_policy


@pytest.mark.django_db
def test_document_index_queryset_tracks_active_plan():
    first_plan = PlanFactory.create()
    second_plan = PlanFactory.create()
    assert first_plan.root_collection is not None
    nested_collection = first_plan.root_collection.add_child(name='Nested documents')
    first_document = AplansDocumentFactory.create(collection=first_plan.root_collection)
    nested_document = AplansDocumentFactory.create(collection=nested_collection)
    other_document = AplansDocumentFactory.create(collection=second_plan.root_collection)
    user = UserFactory.create(is_superuser=True, selected_admin_plan=first_plan)
    request = RequestFactory().get('/admin/documents/')
    request.user = user
    view = IndexView()
    view.setup(request)
    view.needs_usage_count_subquery = False

    assert set(view.get_base_queryset().values_list('pk', flat=True)) == {first_document.pk, nested_document.pk}

    user.selected_admin_plan = second_plan
    user.save(update_fields=['selected_admin_plan'])
    # A subsequent request gets a fresh user and active-plan cache.
    request.user = type(user).objects.get(pk=user.pk)
    assert list(view.get_base_queryset().values_list('pk', flat=True)) == [other_document.pk]
