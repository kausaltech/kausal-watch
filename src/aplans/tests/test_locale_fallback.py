from unittest.mock import MagicMock

from django.conf import settings
from graphql import OperationDefinitionNode, parse

import pytest

from aplans.schema_context import DeterminePlanContextExtension


def _get_operation(query_str: str) -> OperationDefinitionNode:
    doc = parse(query_str)
    op = doc.definitions[0]
    assert isinstance(op, OperationDefinitionNode)
    return op


@pytest.fixture
def extension():
    ext = DeterminePlanContextExtension.__new__(DeterminePlanContextExtension)
    ext.execution_context = MagicMock()
    ext.get_request_headers = MagicMock(return_value={})  # type: ignore[method-assign]
    ext.get_context = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]
    return ext


class TestLocaleFallback:
    def test_falls_back_to_language_code_without_plan_or_directive(self, extension):
        """
        An operation that names no plan and no locale is served in LANGUAGE_CODE.

        Mutations take their plan in the input rather than in a directive, so they
        always land here; the fallback is what decides the language they run under.
        """
        op = _get_operation('mutation { __typename }')

        plan, locale = extension.determine_plan_and_locale(op)

        assert plan is None
        assert locale == settings.LANGUAGE_CODE

    def test_fallback_is_not_merely_the_first_configured_language(self, extension):
        """Guard against falling back to `LANGUAGES[0]`, which is ordered, not preferred."""
        first_configured = settings.LANGUAGES[0][0]
        if first_configured == settings.LANGUAGE_CODE:
            pytest.skip('LANGUAGES[0] coincides with LANGUAGE_CODE; the two are indistinguishable here')

        _plan, locale = extension.determine_plan_and_locale(_get_operation('mutation { __typename }'))

        assert locale != first_configured

    def test_fallback_locale_is_supported(self, extension):
        _plan, locale = extension.determine_plan_and_locale(_get_operation('query { __typename }'))

        assert locale is not None
        assert locale.lower() in {x[0].lower() for x in settings.LANGUAGES}

    def test_context_records_the_fallback_locale(self, extension):
        ctx = extension.get_context()

        _plan, locale = extension.determine_plan_and_locale(_get_operation('mutation { __typename }'))

        assert ctx.graphql_query_language == locale
