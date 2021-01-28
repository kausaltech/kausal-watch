import pytest
from actions.tests.conftest import plan
from indicators.models import Indicator, Unit


@pytest.fixture
def unit():
    return Unit.objects.create(name='unit1')

@pytest.fixture
def indicator(plan, unit):
    obj = Indicator.objects.create(name='indicator1', unit=unit)
    return obj
