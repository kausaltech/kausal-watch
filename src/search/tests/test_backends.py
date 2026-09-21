from __future__ import annotations

import pytest
from modelsearch.backends.base import FilterFieldError

from indicators.models import Indicator
from search.backends import WatchAutocompleteQueryCompiler, WatchSearchQueryCompiler


@pytest.mark.parametrize('compiler_class', [WatchSearchQueryCompiler, WatchAutocompleteQueryCompiler])
def test_indicator_plan_filter_passes_check(compiler_class) -> None:
    qs = Indicator.objects.get_queryset().filter(plans__in=[1])
    compiler_class(qs, 'climate').check()


def test_indicator_plan_filter_targets_the_plans_index_field() -> None:
    qs = Indicator.objects.get_queryset().filter(plans__in=[1, 2])
    compiler = WatchSearchQueryCompiler(qs, 'climate')
    assert compiler._get_filters_from_queryset() == {'terms': {'plans_filter': [1, 2]}}


def test_unindexed_field_still_raises() -> None:
    qs = Indicator.objects.get_queryset().filter(organization__name='Org')
    with pytest.raises(FilterFieldError):
        WatchSearchQueryCompiler(qs, 'climate').check()
