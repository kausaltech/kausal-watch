from unittest.mock import MagicMock

from graphql import OperationDefinitionNode, parse

import pytest

from aplans.graphql_types import WorkflowStateEnum
from aplans.schema import generate_strawberry_schema
from aplans.schema_context import ProcessWorkflowDirectiveExtension


def _get_directive_from_query(query_str: str):
    """Parse a GraphQL query and return the 'workflow' directive from the first operation."""
    doc = parse(query_str)
    op = doc.definitions[0]
    assert isinstance(op, OperationDefinitionNode)
    for d in op.directives:
        if d.name.value == 'workflow':
            return d
    return None


@pytest.fixture
def extension():
    ext = ProcessWorkflowDirectiveExtension.__new__(ProcessWorkflowDirectiveExtension)
    return ext


@pytest.fixture
def mock_schema():
    """Create a mock schema that provides the workflow directive definition."""
    schema = generate_strawberry_schema()
    return schema


def _setup_extension(ext, schema, user, variables=None):
    """Wire up the extension with mocked execution_context and context."""
    exec_ctx = MagicMock()
    exec_ctx.schema._schema = schema._schema
    exec_ctx.variables = variables or {}
    ext.execution_context = exec_ctx

    ctx = MagicMock()
    ctx.get_user.return_value = user
    ext.get_context = MagicMock(return_value=ctx)
    return ctx


class TestProcessWorkflowDirective:
    def test_returns_draft_for_authenticated_user(self, extension, mock_schema):
        directive = _get_directive_from_query('query @workflow(state: DRAFT) { __typename }')
        user = MagicMock()
        user.is_authenticated = True
        _setup_extension(extension, mock_schema, user)

        result = extension.process_workflow_directive(directive)
        assert result == WorkflowStateEnum.DRAFT

    def test_returns_approved_for_authenticated_user(self, extension, mock_schema):
        directive = _get_directive_from_query('query @workflow(state: APPROVED) { __typename }')
        user = MagicMock()
        user.is_authenticated = True
        _setup_extension(extension, mock_schema, user)

        result = extension.process_workflow_directive(directive)
        assert result == WorkflowStateEnum.APPROVED

    def test_returns_published_for_unauthenticated_user(self, extension, mock_schema):
        directive = _get_directive_from_query('query @workflow(state: DRAFT) { __typename }')
        _setup_extension(extension, mock_schema, user=None)

        result = extension.process_workflow_directive(directive)
        assert result == WorkflowStateEnum.PUBLISHED

    def test_defaults_to_published_when_no_state_arg(self, extension, mock_schema):
        directive = _get_directive_from_query('query @workflow { __typename }')
        user = MagicMock()
        user.is_authenticated = True
        _setup_extension(extension, mock_schema, user)

        result = extension.process_workflow_directive(directive)
        assert result == WorkflowStateEnum.PUBLISHED

    def test_returns_draft_when_state_passed_as_variable(self, extension, mock_schema):
        directive = _get_directive_from_query('query ($state: WorkflowState!) @workflow(state: $state) { __typename }')
        user = MagicMock()
        user.is_authenticated = True
        _setup_extension(extension, mock_schema, user, variables={'state': 'DRAFT'})

        result = extension.process_workflow_directive(directive)
        assert result == WorkflowStateEnum.DRAFT
        assert isinstance(result, WorkflowStateEnum)
