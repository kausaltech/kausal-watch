from __future__ import annotations

from unittest import mock

import pytest

from actions.tests.factories import PlanFactory
from indicators.search_indexing import reindex_indicators
from indicators.tests.factories import IndicatorFactory

pytestmark = pytest.mark.django_db


def _backend(language_code: str | None) -> mock.Mock:
    backend = mock.Mock()
    backend.language_code = language_code
    return backend


def test_reindex_indicators_is_a_noop_for_empty_pks():
    """An empty pk list must return without consulting any search backend."""
    with mock.patch('modelsearch.backends.get_search_backends_with_name') as get_backends:
        reindex_indicators([])
    get_backends.assert_not_called()


def test_reindex_indicators_indexes_each_backend_in_its_own_language():
    """
    Each language backend must receive the indicators that belong to its language.

    ``Indicator.get_indexed_objects()`` filters by the current index language, so it is evaluated
    inside each backend's language context -- otherwise indicators belonging only to another
    language's plans are dropped and one language's set is sent to every backend.
    """
    # other_languages defaults to ['fi'] on the factory; clear it so each plan matches only its
    # primary language, isolating the per-backend language filtering under test.
    plan_fi = PlanFactory.create(primary_language='fi', other_languages=[])
    plan_en = PlanFactory.create(primary_language='en', other_languages=[])
    ind_fi = IndicatorFactory.create(plans=[plan_fi])
    ind_en = IndicatorFactory.create(plans=[plan_en])

    fi_backend = _backend('fi')
    en_backend = _backend('en')
    with mock.patch(
        'modelsearch.backends.get_search_backends_with_name',
        return_value=[('default-fi', fi_backend), ('default-en', en_backend)],
    ):
        reindex_indicators([ind_fi.pk, ind_en.pk])

    assert {o.pk for o in fi_backend.add_bulk.call_args.args[1]} == {ind_fi.pk}
    assert {o.pk for o in en_backend.add_bulk.call_args.args[1]} == {ind_en.pk}
    # A cross-language indicator is not "dropped out"; it must not be deleted from the other backend.
    fi_backend.delete.assert_not_called()
    en_backend.delete.assert_not_called()


def test_reindex_indicators_deletes_documents_for_globally_dropped_out_indicators():
    """
    An indicator that is no longer indexable at all must have its stale document deleted.

    Here it is made non-public; the suppressed per-row handler no longer deletes it, so the batched
    reindex must.
    """
    plan = PlanFactory.create(primary_language='en')
    ind = IndicatorFactory.create(plans=[plan], visibility='internal')

    backend = _backend(None)
    with mock.patch(
        'modelsearch.backends.get_search_backends_with_name',
        return_value=[('default', backend)],
    ):
        reindex_indicators([ind.pk])

    backend.add_bulk.assert_not_called()
    assert backend.delete.call_count == 1
    assert backend.delete.call_args.args[0].pk == ind.pk
