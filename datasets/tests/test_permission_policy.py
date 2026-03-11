"""
Tests for ScopeInheritedDatasetPermissionPolicy.

Covered code paths:
  - Superuser always has access
  - Anonymous user never has access
  - Plan admin can access datasets scoped to their plan's actions/categories/indicators
  - Action contact person can access datasets scoped to their action
  - Indicator contact person can access datasets scoped to their indicator
  - User without any relevant role has no access
  - Dataset with no scope: only superuser can access
  - construct_perm_q filters correctly (queryset level)
  - user_can_create respects model/object_id query params
"""
from __future__ import annotations

import uuid

from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

import pytest

from kausal_common.datasets.models import Dataset

from actions.tests.factories import CategoryFactory, CategoryTypeFactory, PlanFactory
from datasets.permission_policy import ScopeInheritedDatasetPermissionPolicy
from datasets.tests.factories import DatasetFactory, DatasetSchemaFactory

pytestmark = pytest.mark.django_db

# Conftest-registered fixtures used here:
#   plan, action, category, indicator          — shared plan scope
#   plan_admin_user                            — plan admin for `plan`
#   action_contact_person_user                 — contact person for `action`
#   indicator_contact                          — IndicatorContactPerson for `indicator`
#   superuser                                  — superuser
#   user                                       — plain non-admin user


@pytest.fixture
def policy():
    return ScopeInheritedDatasetPermissionPolicy()


@pytest.fixture
def action_dataset(action):
    schema = DatasetSchemaFactory.create()
    ct = ContentType.objects.get_for_model(action)
    return DatasetFactory.create(schema=schema, scope=action, scope_content_type=ct, scope_id=action.pk)


@pytest.fixture
def category_dataset(category):
    schema = DatasetSchemaFactory.create()
    ct = ContentType.objects.get_for_model(category)
    return DatasetFactory.create(schema=schema, scope=category, scope_content_type=ct, scope_id=category.pk)


@pytest.fixture
def indicator_dataset(indicator):
    schema = DatasetSchemaFactory.create()
    ct = ContentType.objects.get_for_model(indicator)
    return DatasetFactory.create(schema=schema, scope=indicator, scope_content_type=ct, scope_id=indicator.pk)


@pytest.fixture
def indicator_contact_user(indicator_contact):
    # IndicatorContactFactory creates a Person whose save() auto-creates a User
    return indicator_contact.person.user


# ---------------------------------------------------------------------------
# user_has_perm — action-scoped dataset
# ---------------------------------------------------------------------------

class TestUserHasPermActionScoped:
    def test_superuser(self, policy, superuser, action_dataset):
        assert policy.user_has_perm(superuser, 'change', action_dataset) is True

    def test_plan_admin(self, policy, plan_admin_user, action_dataset):
        assert policy.user_has_perm(plan_admin_user, 'change', action_dataset) is True

    def test_action_contact_person(self, policy, action_contact_person_user, action_dataset):
        assert policy.user_has_perm(action_contact_person_user, 'change', action_dataset) is True

    def test_unrelated_user(self, policy, user, action_dataset):
        assert policy.user_has_perm(user, 'change', action_dataset) is False


# ---------------------------------------------------------------------------
# user_has_perm — category-scoped dataset
# ---------------------------------------------------------------------------

class TestUserHasPermCategoryScoped:
    def test_plan_admin(self, policy, plan_admin_user, category_dataset):
        assert policy.user_has_perm(plan_admin_user, 'change', category_dataset) is True

    def test_unrelated_user(self, policy, user, category_dataset):
        assert policy.user_has_perm(user, 'change', category_dataset) is False


# ---------------------------------------------------------------------------
# user_has_perm — indicator-scoped dataset
# ---------------------------------------------------------------------------

class TestUserHasPermIndicatorScoped:
    def test_plan_admin(self, policy, plan_admin_user, indicator_dataset):
        assert policy.user_has_perm(plan_admin_user, 'change', indicator_dataset) is True

    def test_indicator_contact_person(self, policy, indicator_contact_user, indicator_dataset):
        assert policy.user_has_perm(indicator_contact_user, 'change', indicator_dataset) is True

    def test_unrelated_user(self, policy, user, indicator_dataset):
        assert policy.user_has_perm(user, 'change', indicator_dataset) is False


# ---------------------------------------------------------------------------
# user_has_perm — dataset with no scope
# ---------------------------------------------------------------------------

class TestUserHasPermNoScope:
    def test_superuser_can_access_scopeless_dataset(self, policy, superuser):
        schema = DatasetSchemaFactory.create()
        dataset = Dataset.objects.create(uuid=uuid.uuid4(), schema=schema)
        assert policy.user_has_perm(superuser, 'change', dataset) is True

    def test_regular_user_cannot_access_scopeless_dataset(self, policy, user):
        schema = DatasetSchemaFactory.create()
        dataset = Dataset.objects.create(uuid=uuid.uuid4(), schema=schema)
        assert policy.user_has_perm(user, 'change', dataset) is False


# ---------------------------------------------------------------------------
# anon_has_perm
# ---------------------------------------------------------------------------

class TestAnonHasPerm:
    def test_anon_cannot_view_dataset(self, policy, action_dataset):
        assert policy.anon_has_perm('view', action_dataset) is False

    def test_anon_cannot_change_dataset(self, policy, action_dataset):
        assert policy.anon_has_perm('change', action_dataset) is False


# ---------------------------------------------------------------------------
# construct_perm_q — queryset filtering
# ---------------------------------------------------------------------------

class TestConstructPermQ:
    def test_superuser_sees_all(self, policy, superuser, action_dataset, category_dataset, indicator_dataset):
        q = policy.construct_perm_q(superuser, 'change')
        assert q is not None
        qs = Dataset.objects.filter(q)
        assert action_dataset in qs
        assert category_dataset in qs
        assert indicator_dataset in qs

    def test_plan_admin_sees_own_plan_datasets(
        self, policy, plan_admin_user, action_dataset, category_dataset, indicator_dataset
    ):
        q = policy.construct_perm_q(plan_admin_user, 'change')
        assert q is not None
        qs = Dataset.objects.filter(q)
        assert action_dataset in qs
        assert category_dataset in qs
        assert indicator_dataset in qs

    def test_action_contact_sees_own_action_dataset(
        self, policy, action_contact_person_user, action_dataset
    ):
        # Create a category in a completely different plan to verify it is not accessible
        other_plan = PlanFactory.create()
        other_ct = CategoryTypeFactory.create(plan=other_plan)
        other_category = CategoryFactory.create(type=other_ct)
        other_schema = DatasetSchemaFactory.create()
        ct = ContentType.objects.get_for_model(other_category)
        other_category_dataset = DatasetFactory.create(
            schema=other_schema, scope=other_category, scope_content_type=ct, scope_id=other_category.pk
        )

        q = policy.construct_perm_q(action_contact_person_user, 'change')
        assert q is not None
        qs = Dataset.objects.filter(q)
        assert action_dataset in qs
        assert other_category_dataset not in qs

    def test_action_contact_sees_own_action_dataset_via_perm_q(
        self, policy, action_contact_person_user, action_dataset
    ):
        q = policy.construct_perm_q(action_contact_person_user, 'change')
        assert q is not None
        qs = Dataset.objects.filter(q)
        assert action_dataset in qs

    def test_indicator_contact_sees_own_indicator_dataset(
        self, policy, indicator_contact_user, indicator_dataset
    ):
        q = policy.construct_perm_q(indicator_contact_user, 'change')
        assert q is not None
        qs = Dataset.objects.filter(q)
        assert indicator_dataset in qs

    def test_unrelated_user_sees_nothing(
        self, policy, user, action_dataset, category_dataset, indicator_dataset
    ):
        q = policy.construct_perm_q(user, 'change')
        assert q is not None
        qs = Dataset.objects.filter(q)
        assert action_dataset not in qs
        assert category_dataset not in qs
        assert indicator_dataset not in qs

    def test_anon_returns_none(self, policy):
        assert policy.construct_perm_q_anon('change') is None


# ---------------------------------------------------------------------------
# user_can_create
# ---------------------------------------------------------------------------

class TestUserCanCreate:
    def _request(self, model=None, object_id=None):
        rf = RequestFactory()
        params = {}
        if model is not None:
            params['model'] = model
        if object_id is not None:
            params['object_id'] = str(object_id)
        return rf.get('/', params)

    def test_superuser_can_always_create(self, policy, superuser):
        assert policy.user_can_create(superuser) is True

    def test_no_context_returns_false(self, policy, plan_admin_user):
        assert policy.user_can_create(plan_admin_user, context=None) is False

    def test_missing_params_returns_false(self, policy, plan_admin_user):
        request = self._request()
        assert policy.user_can_create(plan_admin_user, context=request) is False

    def test_plan_admin_can_create_action_dataset(self, policy, plan_admin_user, action):
        request = self._request(model='actions.Action', object_id=action.pk)
        assert policy.user_can_create(plan_admin_user, context=request) is True

    def test_unrelated_user_cannot_create_action_dataset(self, policy, user, action):
        request = self._request(model='actions.Action', object_id=action.pk)
        assert policy.user_can_create(user, context=request) is False

    def test_nonexistent_action_returns_false(self, policy, plan_admin_user):
        request = self._request(model='actions.Action', object_id=999999)
        assert policy.user_can_create(plan_admin_user, context=request) is False

    def test_plan_admin_can_create_category_dataset(self, policy, plan_admin_user, category):
        request = self._request(model='actions.Category', object_id=category.pk)
        assert policy.user_can_create(plan_admin_user, context=request) is True

    def test_nonexistent_category_returns_false(self, policy, plan_admin_user):
        request = self._request(model='actions.Category', object_id=999999)
        assert policy.user_can_create(plan_admin_user, context=request) is False

    def test_plan_admin_can_create_indicator_dataset(self, policy, plan_admin_user, indicator):
        request = self._request(model='indicators.Indicator', object_id=indicator.pk)
        assert policy.user_can_create(plan_admin_user, context=request) is True

    def test_nonexistent_indicator_returns_false(self, policy, plan_admin_user):
        request = self._request(model='indicators.Indicator', object_id=999999)
        assert policy.user_can_create(plan_admin_user, context=request) is False

    def test_unknown_model_returns_false(self, policy, plan_admin_user, action):
        request = self._request(model='unknown.Model', object_id=action.pk)
        assert policy.user_can_create(plan_admin_user, context=request) is False
