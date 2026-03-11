from __future__ import annotations

from typing import TYPE_CHECKING, override

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, QuerySet
from django.http import HttpRequest

from kausal_common.datasets.models import (
    DataPoint,
    Dataset,
    DatasetQuerySet,
    DatasetSchema,
    DataSource,
)
from kausal_common.models.permission_policy import ModelPermissionPolicy

from actions.models import Action, Category, Plan
from indicators.models import Indicator

if TYPE_CHECKING:
    from kausal_common.models.permission_policy import ObjectSpecificAction

    from users.models import User


class ScopeInheritedDatasetPermissionPolicy(ModelPermissionPolicy[Dataset, HttpRequest, DatasetQuerySet]):
    """Permission policy for datasets that inherits permissions from the dataset's scope object."""

    def __init__(self):
        from kausal_common.datasets.models import Dataset
        super().__init__(model=Dataset)

    def construct_perm_q(self, user: User, action: ObjectSpecificAction) -> Q | None:
        if user.is_superuser:
            return Q()

        action_ct = ContentType.objects.get_for_model(Action)
        category_ct = ContentType.objects.get_for_model(Category)
        indicator_ct = ContentType.objects.get_for_model(Indicator)

        editable_actions = Action.objects.qs.modifiable_by(user)
        editable_categories = Category.objects.filter(type__plan__in=user.get_adminable_plans())
        editable_indicators = Indicator.objects.qs.modifiable_by(user)

        return Q(
            Q(scope_content_type=action_ct, scope_id__in=editable_actions) |
            Q(scope_content_type=category_ct, scope_id__in=editable_categories) |
            Q(scope_content_type=indicator_ct, scope_id__in=editable_indicators)
        )

    def construct_perm_q_anon(self, action: ObjectSpecificAction) -> Q | None:
        return None

    def user_has_perm(self, user: User, action: ObjectSpecificAction, obj: Dataset) -> bool:
        """Check if user has permission to perform an action on an instance."""
        if user.is_superuser:
            return True

        # If no scope is set, only superusers can access
        if obj.scope is None:
            return False

        if isinstance(obj.scope, Action):
            return user.can_modify_action(obj.scope)

        if isinstance(obj.scope, Category):
            return obj.scope.type.plan in user.get_adminable_plans()

        if isinstance(obj.scope, Indicator):
            return user.can_modify_indicator(obj.scope)

        return False

    def anon_has_perm(self, action: ObjectSpecificAction, obj: Dataset) -> bool:
        """Check if an unauthenticated user has permission to perform an action on an instance."""
        return False

    def user_can_create(self, user: User, context: None | HttpRequest = None) -> bool:
        """
        Check if user can create a new dataset.

        Since datasets are always connected to a scope object,
        a user can create a dataset if they can edit the scope object
        the dataset will be connected to.
        """
        if user.is_superuser:
            return True

        if context is None:
            return False

        model = context.GET.get('model')
        object_id = context.GET.get('object_id')

        # We currently support creating datasets in Watch only when attaching them to objects
        if model is None or object_id is None:
            return False

        if model == 'actions.Action':
            try:
                action = Action.objects.get(pk=object_id)
            except Action.DoesNotExist:
                return False
            return user.can_modify_action(action)

        if model == 'actions.Category':
            try:
                category = Category.objects.get(pk=object_id)
            except Category.DoesNotExist:
                return False
            return user.can_modify_category(category)

        if model == 'indicators.Indicator':
            try:
                indicator = Indicator.objects.get(pk=object_id)
            except Indicator.DoesNotExist:
                return False
            return user.can_modify_indicator(indicator)

        return False


class DataPointPermissionPolicy(ModelPermissionPolicy[DataPoint, None, QuerySet[DataPoint]]):
    """Permission policy for data points that inherits permissions from the parent dataset."""

    def __init__(self):
        from kausal_common.datasets.models import DataPoint
        super().__init__(DataPoint)

    def construct_perm_q(self, user: User, action: ObjectSpecificAction) -> Q | None:
        """Grant permission to data points if the user can access the parent dataset."""
        if user.is_superuser:
            return Q()

        # Use the dataset permission policy to determine which datasets the user can access
        dataset_policy = ScopeInheritedDatasetPermissionPolicy()

        # Get datasets the user can view or edit based on the requested action
        if action == 'view':
            accessible_datasets = Dataset.objects.filter(dataset_policy.construct_perm_q(user, 'view'))
        else:
            accessible_datasets = Dataset.objects.filter(dataset_policy.construct_perm_q(user, 'change'))

        return Q(dataset__in=accessible_datasets)

    def construct_perm_q_anon(self, action: ObjectSpecificAction) -> Q | None:
        """Anonymous users can only view data points if they can view the parent dataset."""
        if action == 'view':
            dataset_policy = ScopeInheritedDatasetPermissionPolicy()
            viewable_datasets = Dataset.objects.filter(dataset_policy.construct_perm_q_anon('view'))
            return Q(dataset__in=viewable_datasets)
        return None

    def user_has_perm(self, user: User, action: ObjectSpecificAction, obj: DataPoint) -> bool:
        """Check if user has permission based on the parent dataset."""
        if user.is_superuser:
            return True

        dataset_policy = ScopeInheritedDatasetPermissionPolicy()

        # For viewing, check if user can view the dataset
        if action == 'view':
            return dataset_policy.user_has_perm(user, 'view', obj.dataset)

        # For editing/deleting, check if user can modify the dataset
        return dataset_policy.user_has_perm(user, 'change', obj.dataset)

    def anon_has_perm(self, action: ObjectSpecificAction, obj: DataPoint) -> bool:
        """Check if anonymous users can access the data point based on the parent dataset."""
        if action != 'view':
            return False

        dataset_policy = ScopeInheritedDatasetPermissionPolicy()
        return dataset_policy.anon_has_perm('view', obj.dataset)

    def user_can_create(self, user: User, context: None) -> bool:
        """
        Check if user can create new data points.

        A user can create data points if they can edit at least one dataset.
        """
        if user.is_superuser:
            return True
        dataset_policy = ScopeInheritedDatasetPermissionPolicy()

        # Check if user can edit any datasets
        return Dataset.objects.filter(
            dataset_policy.construct_perm_q(user, 'change')
        ).exists()


class DatasetSchemaPermissionPolicy(ModelPermissionPolicy[DatasetSchema, None, QuerySet[DatasetSchema]]):
    # To be implemented; creating schemas in the UI is not yet supported in Watch

    def __init__(self):
        from kausal_common.datasets.models import DatasetSchema
        super().__init__(model=DatasetSchema)

    def construct_perm_q(self, user: User, action: ObjectSpecificAction) -> Q | None:
        if user.is_superuser:
            return Q()

        # Get ContentTypes for Plan and Category
        plan_ct = ContentType.objects.get_for_model(Plan)
        category_ct = ContentType.objects.get_for_model(Category)

        adminable_plans = user.get_adminable_plans()
        adminable_categories = Category.objects.filter(type__plan__in=adminable_plans)

        return Q(
            Q(scopes__scope_content_type=plan_ct, scopes__scope_id__in=adminable_plans) |
            Q(scopes__scope_content_type=category_ct, scopes__scope_id__in=adminable_categories)
        )

    def construct_perm_q_anon(self, action: ObjectSpecificAction) -> Q | None:
        return None

    def user_has_perm(self, user: User, action: ObjectSpecificAction, obj: DatasetSchema) -> bool:
        """Check if user has permission to perform an action on a dataset schema instance."""
        if user.is_superuser:
            return True
        return False

    def anon_has_perm(self, action: ObjectSpecificAction, obj: DatasetSchema) -> bool:
        return False

    def user_can_create(self, user: User, context: None) -> bool:
        """
        Check if user can create a new dataset schema.

        A user can create a dataset schema if they are a general plan admin for any plan.
        """
        if user.is_superuser:
            return True
        return False


class DataSourcePermissionPolicy(ModelPermissionPolicy[DataSource, None, QuerySet[DataSource]]):
    # FIXME: This placeholder policy is there to prevent tests from blowing up as DataSourceViewSet, which will be
    # instantiated, requires a permission policy. KW does not seem to use data sources yet, but once it does, we should
    # implement this permission policy.

    def __init__(self):
        from kausal_common.datasets.models import DataSource
        super().__init__(model=DataSource)

    @override
    def construct_perm_q(self, user: User, action: ObjectSpecificAction) -> Q | None:
        return None

    @override
    def construct_perm_q_anon(self, action: ObjectSpecificAction) -> Q | None:
        return None

    @override
    def user_has_perm(self, user: User, action: ObjectSpecificAction, obj: DataSource) -> bool:
        return False

    @override
    def anon_has_perm(self, action: ObjectSpecificAction, obj: DataSource) -> bool:
        return False

    @override
    def user_can_create(self, user: User, context: None) -> bool:
        return False
