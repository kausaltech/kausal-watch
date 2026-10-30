from django.core.exceptions import ImproperlyConfigured
from wagtail.permission_policies.base import ModelPermissionPolicy
from wagtail.permissions import policy_registry

import pytest

from kausal_common.datasets.models import DataPoint, Dataset, DatasetSchema, DataSource

from actions.category_permissions import CategoryPermissionPolicy
from actions.models import (
    ActionChangeLogMessage,
    ActionImpact,
    Category,
    CategoryChangeLogMessage,
    CategoryType,
    CommonCategoryType,
    IndicatorChangeLogMessage,
    Plan,
    PlanFeatures,
    Pledge,
    PublicUser,
)
from actions.pledge_permissions import ParticipantsPermissionPolicy, PledgePermissionPolicy
from admin_site.models import BuiltInFieldCustomization
from admin_site.permissions import (
    PlanAdminOnlyPermissionPolicy,
    PlanRelatedPermissionPolicy,
    PlanSpecificSingletonModelPermissionPolicy,
    PlanSpecificSingletonModelSuperuserPermissionPolicy,
    SuperuserOnlyPermissionPolicy,
)
from admin_site.viewsets import WatchViewSet
from content.models import SiteGeneralContent
from content.permissions import SiteGeneralContentPermissionPolicy
from documents.models import AplansDocument
from feedback.models import UserFeedback
from feedback.permissions import UserFeedbackPermissionPolicy
from images.models import AplansImage
from indicators.models import Dimension, IndicatorGoalDataPoint
from indicators.permission_policy import DimensionPermissionPolicy
from notifications.models import BaseTemplate, NotificationSettings
from orgs.models import Organization
from pages.models import PageChangeLogMessage
from reports.models import Report, ReportType


@pytest.mark.parametrize(
    'model',
    [AplansImage, AplansDocument, Dataset, DataSource, DatasetSchema, DataPoint, IndicatorGoalDataPoint, Organization],
)
def test_declared_permission_policy_is_registered(model):
    registered = policy_registry.get_by_type(model, fallback=False)
    assert type(registered) is type(model.permission_policy())


@pytest.mark.parametrize(
    ('model', 'policy_class'),
    [
        (Pledge, PledgePermissionPolicy),
        (PublicUser, ParticipantsPermissionPolicy),
        (BuiltInFieldCustomization, PlanAdminOnlyPermissionPolicy),
        (PlanFeatures, PlanSpecificSingletonModelPermissionPolicy),
        (NotificationSettings, PlanSpecificSingletonModelSuperuserPermissionPolicy),
        (SiteGeneralContent, SiteGeneralContentPermissionPolicy),
        (UserFeedback, UserFeedbackPermissionPolicy),
        (BaseTemplate, PlanRelatedPermissionPolicy),
        (ActionChangeLogMessage, PlanRelatedPermissionPolicy),
        (IndicatorChangeLogMessage, PlanRelatedPermissionPolicy),
        (CategoryChangeLogMessage, PlanRelatedPermissionPolicy),
        (PageChangeLogMessage, PlanRelatedPermissionPolicy),
        (ReportType, PlanRelatedPermissionPolicy),
        (Report, PlanRelatedPermissionPolicy),
        (Dimension, DimensionPermissionPolicy),
        (CommonCategoryType, SuperuserOnlyPermissionPolicy),
        (CategoryType, PlanAdminOnlyPermissionPolicy),
        (Category, CategoryPermissionPolicy),
    ],
)
def test_viewset_models_keep_their_permission_policy(model, policy_class):
    assert type(policy_registry.get_by_type(model, fallback=False)) is policy_class


def test_plan_keeps_wagtail_default_permission_policy():
    assert type(policy_registry.get_by_type(Plan)) is ModelPermissionPolicy


def test_watch_viewset_requires_a_permission_policy_for_plan_related_models():
    viewset = type('ActionImpactViewSet', (WatchViewSet,), {'model': ActionImpact})()
    with pytest.raises(ImproperlyConfigured, match='needs a permission_policy'):
        viewset.register_permissions()
