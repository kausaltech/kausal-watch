import pytest

from actions.wagtail_admin import PlanAdmin
from admin_site.tests.factories import ClientFactory

pytestmark = pytest.mark.django_db


class TestPlanOrganizationPanel:
    def _find_field_panel(self, container, field_name):
        """Recursively find a FieldPanel by field_name."""
        for child in getattr(container, 'children', []):
            if getattr(child, 'field_name', None) == field_name:
                return child
            result = self._find_field_panel(child, field_name)
            if result is not None:
                return result
        return None

    def _get_create_edit_handler(self, rf, superuser):
        from aplans.context_vars import ctx_instance, ctx_request

        from actions.models import Plan

        request = rf.get('/')
        request.user = superuser
        instance = Plan()

        with ctx_request.activate(request), ctx_instance.activate(instance):
            admin = PlanAdmin()
            return admin.get_edit_handler()

    def _get_create_form_class(self, rf, superuser):
        from aplans.context_vars import ctx_instance, ctx_request

        from actions.models import Plan

        request = rf.get('/')
        request.user = superuser
        instance = Plan()

        with ctx_request.activate(request), ctx_instance.activate(instance):
            admin = PlanAdmin()
            edit_handler = admin.get_edit_handler()
            bound = edit_handler.bind_to_model(Plan)
            return bound.get_form_class()

    def _base_plan_data(self, **overrides):
        client = ClientFactory.create()
        data = {
            'name': 'Test Plan',
            'identifier': 'test-plan',
            'primary_language': 'en',
            'other_languages': [],
            'country': 'FI',
            'usage_status': 'customer_use',
            # Inline formset management data for the 'clients' InlinePanel
            'clients-TOTAL_FORMS': '1',
            'clients-INITIAL_FORMS': '0',
            'clients-MIN_NUM_FORMS': '1',
            'clients-MAX_NUM_FORMS': '1000',
            'clients-0-client': str(client.pk),
            'clients-0-ORDER': '0',
        }
        data.update(overrides)
        return data

    def test_create_form_has_organization_name_field(self, rf, superuser):
        edit_handler = self._get_create_edit_handler(rf, superuser)
        panel = self._find_field_panel(edit_handler, 'organization_name')
        assert panel is not None, 'organization_name panel not found in create panels'

    def test_organization_not_required_when_creating(self, rf, superuser):
        from actions.models import Plan

        form_class = self._get_create_form_class(rf, superuser)
        form = form_class(data={}, instance=Plan())
        assert not form.fields['organization'].required

    def test_neither_org_nor_name_provided_is_invalid(self, rf, superuser):
        from actions.models import Plan

        form_class = self._get_create_form_class(rf, superuser)
        form = form_class(data=self._base_plan_data(), instance=Plan())
        assert not form.is_valid()

    def test_org_name_only_is_valid(self, rf, superuser):
        from actions.models import Plan

        form_class = self._get_create_form_class(rf, superuser)
        data = self._base_plan_data(organization_name='New Org')
        form = form_class(data=data, instance=Plan())
        is_valid = form.is_valid()
        assert is_valid, form.errors

    def test_org_selected_only_is_valid(self, rf, superuser):
        from actions.models import Plan
        from orgs.tests.factories import OrganizationFactory

        org = OrganizationFactory.create()
        form_class = self._get_create_form_class(rf, superuser)
        data = self._base_plan_data(organization=org.pk)
        form = form_class(data=data, instance=Plan())
        is_valid = form.is_valid()
        assert is_valid, form.errors

    def test_both_provided_is_invalid(self, rf, superuser):
        from actions.models import Plan
        from orgs.tests.factories import OrganizationFactory

        org = OrganizationFactory.create()
        form_class = self._get_create_form_class(rf, superuser)
        data = self._base_plan_data(organization=org.pk, organization_name='New Org')
        form = form_class(data=data, instance=Plan())
        assert not form.is_valid()

    def test_primary_language_empty_by_default_when_creating(self, rf, superuser):
        from actions.models import Plan

        form_class = self._get_create_form_class(rf, superuser)
        form = form_class(instance=Plan())
        assert not form['primary_language'].value(), 'Rendered value should be empty'
        choices = list(form.fields['primary_language'].choices)
        assert choices[0][0] == '', 'First choice should be an empty value'

    def test_primary_language_required_when_creating(self, rf, superuser):
        from actions.models import Plan

        form_class = self._get_create_form_class(rf, superuser)
        data = self._base_plan_data(primary_language='')
        form = form_class(data=data, instance=Plan())
        assert not form.is_valid()
        assert 'primary_language' in form.errors

    def test_save_with_org_name_creates_organization(self, rf, superuser):
        from actions.models import Plan

        form_class = self._get_create_form_class(rf, superuser)
        data = self._base_plan_data(organization_name='Helsinki', primary_language='fi')
        form = form_class(data=data, instance=Plan())
        assert form.is_valid(), form.errors

        plan = form.save()
        assert plan.organization is not None
        assert plan.organization.name == 'Helsinki'
        assert plan.organization.primary_language == 'fi'
        assert plan.organization.depth == 1  # root node

    def _validate_form_with_request(self, rf, superuser, form):
        from django.contrib.messages.storage.fallback import FallbackStorage

        from aplans.context_vars import ctx_instance, ctx_request

        request = rf.get('/')
        request.user = superuser
        request.session = 'session'
        messages_storage = FallbackStorage(request)
        request._messages = messages_storage

        with ctx_request.activate(request), ctx_instance.activate(form.instance):
            is_valid = form.is_valid()
        return is_valid, messages_storage

    def test_clean_warns_when_org_language_differs_from_plan(self, rf, superuser):
        from actions.models import Plan
        from orgs.tests.factories import OrganizationFactory

        org = OrganizationFactory.create(primary_language='fi')
        form_class = self._get_create_form_class(rf, superuser)
        data = self._base_plan_data(organization=org.pk, primary_language='en')
        form = form_class(data=data, instance=Plan())

        is_valid, messages_storage = self._validate_form_with_request(rf, superuser, form)
        assert is_valid, form.errors
        warning_messages = [m for m in messages_storage if m.level_tag == 'warning']
        assert len(warning_messages) == 1

    def test_clean_no_warning_when_org_language_matches_plan(self, rf, superuser):
        from actions.models import Plan
        from orgs.tests.factories import OrganizationFactory

        org = OrganizationFactory.create(primary_language='en')
        form_class = self._get_create_form_class(rf, superuser)
        data = self._base_plan_data(organization=org.pk, primary_language='en')
        form = form_class(data=data, instance=Plan())

        is_valid, messages_storage = self._validate_form_with_request(rf, superuser, form)
        assert is_valid, form.errors
        warning_messages = [m for m in messages_storage if m.level_tag == 'warning']
        assert len(warning_messages) == 0
