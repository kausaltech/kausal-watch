from pprint import pprint as pr
import pytest

from .fixtures import *


pytestmark = pytest.mark.django_db


def test_foo(plan_with_actions_having_attributes):
    pr(plan_with_actions_having_attributes)
    assert True
