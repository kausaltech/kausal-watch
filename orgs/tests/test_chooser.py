import pytest

from orgs.chooser import OrganizationChooserViewSet
from orgs.tests.factories import OrganizationFactory

pytestmark = pytest.mark.django_db


class TestOrganizationChooserViewSet:
    def _get_viewset_instance(self):
        from orgs.chooser import organization_chooser_viewset

        return organization_chooser_viewset

    def test_inherits_from_builtin_chooser_viewset(self):
        from kausal_common.admin_site.choosers import ChooserViewSet

        assert issubclass(OrganizationChooserViewSet, ChooserViewSet)

    def test_has_no_creation_form_class(self):
        vs = self._get_viewset_instance()
        assert not hasattr(vs, 'creation_form_class') or vs.creation_form_class is None

    def test_get_object_list_returns_root_nodes(self):
        vs = self._get_viewset_instance()
        root_org = OrganizationFactory.create()
        _child_org = OrganizationFactory.create(parent=root_org)
        result = vs.get_object_list(view=None)
        org_ids = [o.pk for o in result]
        assert root_org.pk in org_ids
        assert _child_org.pk not in org_ids

    def test_get_object_list_filters_by_search(self, rf):
        vs = self._get_viewset_instance()
        OrganizationFactory.create(name='City of Helsinki')
        OrganizationFactory.create(name='City of Espoo')

        class FakeView:
            def __init__(self, request):
                self.request = request

        request = rf.get('/', {'q': 'Helsinki'})
        view = FakeView(request)
        result = vs.get_object_list(view=view)
        names = [o.name for o in result]
        assert 'City of Helsinki' in names
        assert 'City of Espoo' not in names

    def test_widget_class_is_generated(self):
        vs = self._get_viewset_instance()
        assert vs.widget_class is not None


class TestOrganizationChooserCreateViewIntegration:
    def test_search_results_with_query(self, client, superuser):
        """Searching in the chooser should not crash (regression: FilterFieldError on depth)."""
        client.force_login(superuser)
        OrganizationFactory.create(name='City of Helsinki')

        response = client.get('/admin/organization-chooser/results/?q=Helsinki')
        assert response.status_code == 200
