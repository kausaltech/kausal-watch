from wagtail.permission_policies.base import ModelPermissionPolicy
from wagtail.permissions import policy_registry

import pytest

from kausal_common.datasets.models import DataPoint, Dataset, DatasetSchema, DataSource

from actions.models import Plan
from documents.models import AplansDocument
from images.models import AplansImage
from indicators.models import IndicatorGoalDataPoint
from orgs.models import Organization


@pytest.mark.parametrize(
    'model',
    [AplansImage, AplansDocument, Dataset, DataSource, DatasetSchema, DataPoint, IndicatorGoalDataPoint, Organization],
)
def test_declared_permission_policy_is_registered(model):
    registered = policy_registry.get_by_type(model, fallback=False)
    assert type(registered) is type(model.permission_policy())


def test_plan_keeps_wagtail_default_permission_policy():
    assert type(policy_registry.get_by_type(Plan)) is ModelPermissionPolicy
