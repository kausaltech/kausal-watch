from __future__ import annotations

from factory import Sequence, SubFactory
from factory.django import DjangoModelFactory

from access_requests.models import AccessRequest
from actions.models import Plan
from actions.tests.factories import PlanFactory


class AccessRequestFactory(DjangoModelFactory[AccessRequest]):
    class Meta:
        model = 'access_requests.AccessRequest'

    plan = SubFactory[AccessRequest, Plan](PlanFactory)
    email = Sequence(lambda i: f'visitor{i}@example.com')
