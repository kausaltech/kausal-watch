from typing import TYPE_CHECKING, Annotated, Any

from fastmcp import Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from mcp_server.__generated__.schema import (
    ActionAttributeUpdateInput,
    ActionAttributeValueInput,
    ActionDetails,
    ActionInput,
    ActionLinkInput,
    ActionResponsiblePartyInput,
    ActionUpdateInput,
    AttributeValueChoiceInput,
    CreateAction,
    GetActions,
    ListActions,
    UpdateAction,
    UpdateActions,
)

from .helpers import (
    check_operation_result,
    execute_operation,
    execute_schema_query,
    register_tool,
    require_mcp_plan_write_authorization,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP


@register_tool(annotations=ToolAnnotations(title='List actions in a plan', readOnlyHint=True, openWorldHint=False))
async def list_actions(
    plan: Annotated[str, "The plan identifier (e.g., 'sunnydale', 'tampere-ilmasto')"],
    category: Annotated[str | None, 'Filter by category ID (includes descendants)'] = None,
    first: Annotated[int | None, 'Limit number of results (default: all)'] = None,
    order_by: Annotated[str | None, "Order by field: 'updated_at' or 'identifier'"] = None,
) -> str:
    """
    List actions from a climate action plan with optional filtering.

    Returns a compact list of actions with identifier, name, status, and primary organization.
    Use get_actions(ids) for full details on specific actions.
    """
    result = await execute_operation(
        ListActions,
        ListActions.Arguments(plan=plan, category=category, first=first, orderBy=order_by),
    )

    if result.plan_actions is None:
        raise ToolError(f"Plan '{plan}' not found or not accessible")

    lines: list[str] = []
    for action in result.plan_actions:
        parts = [f'{action.identifier} (id:{action.id}): {action.name}']

        # Add status
        if action.status_summary:
            parts.append(f'[{action.status_summary.label}]')

        # Add primary org
        if action.primary_org:
            org_name = action.primary_org.abbreviation or action.primary_org.name
            parts.append(f'({org_name})')

        lines.append(' '.join(parts))

    return '\n'.join(lines)


@register_tool(
    annotations=ToolAnnotations(title='Get detailed information about action(s)', readOnlyHint=True, openWorldHint=False)
)
async def get_actions(
    ids: Annotated[list[str], 'List of action IDs to fetch'],
) -> list[ActionDetails]:
    """
    Get detailed information about multiple actions by their IDs.

    Returns comprehensive action details including status, organizations,
    tasks, indicators, and more. Use list_actions to discover action IDs first.
    """
    result = await execute_operation(GetActions, GetActions.Arguments(ids=ids))
    return result.admin.actions


def parse_and_validate_action_query(query: str):
    from graphql.language.parser import parse
    from graphql.validation import validate

    from aplans.schema import schema

    document = parse(query)
    errors = validate(schema._schema, document, max_errors=5)
    if errors:
        error_msgs = '; '.join(str(e) for e in errors)
        raise ToolError(f'GraphQL fragment validation failed: {error_msgs}')

    defs = document.to_dict()['definitions']
    if len(defs) != 2 or defs[0]['kind'] != 'operation_definition' or defs[1]['kind'] != 'fragment_definition':
        raise ToolError('Invalid action query: expected exactly one operation and one fragment definition')

    op_def = defs[0]
    frag_def = defs[1]
    if op_def.get('operation') != 'query':
        raise ToolError('Invalid action query: operation must be a query')
    if frag_def.get('name', {}).get('value') != 'FreeformActionFields':
        raise ToolError('Invalid action query: unexpected fragment name')
    if frag_def.get('type_condition', {}).get('name', {}).get('value') != 'Action':
        raise ToolError('Invalid action query: fragment must target the Action type')

    return document


@register_tool(annotations=ToolAnnotations(title='Query actions in a plan', readOnlyHint=True, openWorldHint=False))
async def query_actions(
    plan: Annotated[str, "The plan identifier (e.g., 'sunnydale', 'bremen-klima-copy1')"],
    fields: Annotated[
        str,
        'GraphQL fields to select (fragment body on Action type). Read schema://action-fields for available fields.',
    ],
    category: Annotated[str | None, 'Filter by category ID (includes descendants)'] = None,
    first: Annotated[int | None, 'Limit number of results'] = None,
) -> list[dict[str, Any]]:
    """
    Query actions with custom field selection.

    Use this for flexible queries when you need specific fields or want to filter/analyze
    actions based on their attributes. Read the schema://action-fields resource first
    to see available fields.

    Example fields parameter:
        identifier
        name
        statusSummary { label sentiment }
        attributes {
            ... on AttributeChoice {
                type { identifier }
                choice { identifier name }
            }
        }
    """

    # Build the query with the provided fields
    # The @context directive activates the correct plan context for language and permissions
    query = (
        """
    query MCPQueryActions($plan: ID!, $category: ID, $first: Int) @context(input: {identifier: $plan}) {
        planActions(plan: $plan, category: $category, first: $first) {
            ...FreeformActionFields
        }
    }
    fragment FreeformActionFields on Action {
        %s
    }"""
        % fields
    )

    parse_and_validate_action_query(query)

    variables: dict[str, Any] = {'plan': plan}
    if category is not None:
        variables['category'] = category
    if first is not None:
        variables['first'] = first

    result = await execute_schema_query(query, variables)

    if result.errors:
        error_msgs = '; '.join(str(e) for e in result.errors)
        raise ToolError(f'GraphQL query failed: {error_msgs}')

    if result.data is None:
        raise ToolError('No data returned from query')

    return result.data.get('planActions', [])


@register_tool(annotations=ToolAnnotations(title='Create a new action in a plan'))
async def create_action(
    plan_id: Annotated[str, 'The ID (pk or identifier) of the plan to create the action in'],
    name: Annotated[str, 'Name of the action'],
    identifier: Annotated[str | None, 'Action identifier (required if plan has action identifiers enabled)'] = None,
    description: Annotated[str | None, 'Detailed description of the action'] = None,
    primary_org_id: Annotated[str | None, 'ID of the primary responsible organization'] = None,
    category_ids: Annotated[list[str] | None, 'List of category IDs to assign to the action'] = None,
    attribute_values: Annotated[
        list[ActionAttributeUpdateInput] | None, 'List of attribute values to assign to the action'
    ] = None,
    ctx: Context | None = None,
) -> ActionDetails:
    """
    Create a new action in a plan.

    Use get_plan to check if the plan requires action identifiers (hasActionIdentifiers feature).
    Use list_organizations to find organization IDs for primary_org_id.
    """
    if ctx is None:
        raise ToolError('Context is required for write authorization.')
    await require_mcp_plan_write_authorization(plan_ref=plan_id, tool_name='create_action', ctx=ctx)

    result = await execute_operation(
        CreateAction,
        CreateAction.Arguments(
            input=ActionInput(
                planId=plan_id,
                name=name,
                identifier=identifier or '',
                description=description,
                primaryOrgId=primary_org_id,
                categoryIds=category_ids,
                attributeValues=attribute_values,
            )
        ),
    )

    return check_operation_result(result.action.create_action)


@register_tool(annotations=ToolAnnotations(title='Update a single action in a plan', idempotentHint=True))
async def update_action(
    plan_id: Annotated[str, 'The ID (pk or identifier) of the plan'],
    id: Annotated[str, 'The action ID (pk) or identifier'],
    description: Annotated[str | None, 'HTML description of the action'] = None,
    lead_paragraph: Annotated[str | None, 'Plain text lead paragraph'] = None,
    category_ids: Annotated[list[str] | None, 'List of category IDs to assign (replaces existing)'] = None,
    responsible_parties: Annotated[
        list[ActionResponsiblePartyInput] | None, 'List of responsible parties (replaces existing)'
    ] = None,
    links: Annotated[list[ActionLinkInput] | None, 'List of links (replaces existing)'] = None,
    ctx: Context | None = None,
) -> ActionDetails:
    """
    Update a single action's core fields and return its full details.

    Only provided fields are changed; omitted fields are left as-is.
    For list fields (categories, responsible_parties, links), the provided list
    replaces the existing values.

    IMPORTANT: Do NOT use this tool to set attribute values (rich text, choice, etc.).
    Use update_action_attribute instead — it accepts each value as a simple top-level
    parameter, which avoids serialization issues with nested JSON/HTML content.

    Use list_actions to discover action IDs, and get_plan to find attribute type IDs and
    choice option IDs.
    """
    if ctx is None:
        raise ToolError('Context is required for write authorization.')
    await require_mcp_plan_write_authorization(plan_ref=plan_id, tool_name='update_action', ctx=ctx)

    input_kwargs: dict[str, Any] = {'id': id}
    if description is not None:
        input_kwargs['description'] = description
    if lead_paragraph is not None:
        input_kwargs['leadParagraph'] = lead_paragraph
    if category_ids is not None:
        input_kwargs['categoryIds'] = category_ids
    if responsible_parties is not None:
        input_kwargs['responsibleParties'] = responsible_parties
    if links is not None:
        input_kwargs['links'] = links

    result = await execute_operation(
        UpdateAction,
        UpdateAction.Arguments(
            planId=plan_id,  # type: ignore[call-arg]
            input=ActionUpdateInput(**input_kwargs),
        ),
    )
    return check_operation_result(result.action.update_action)


@register_tool(annotations=ToolAnnotations(title='Update an attribute for a single action in a plan', idempotentHint=True))
async def update_action_attribute(
    plan_id: Annotated[str, 'The ID (pk or identifier) of the plan'],
    action_id: Annotated[str, 'The action ID (pk) or identifier'],
    attribute_type_id: Annotated[
        str, 'The attribute type ID (pk or identifier). Use get_plan to discover available attribute types.'
    ],
    rich_text: Annotated[str | None, 'HTML rich text value (for RICH_TEXT attributes)'] = None,
    choice_id: Annotated[str | None, 'Choice option ID (for ORDERED_CHOICE / UNORDERED_CHOICE attributes)'] = None,
    text: Annotated[str | None, 'Plain text value (for TEXT attributes)'] = None,
    ctx: Context | None = None,
) -> str:
    """
    Set a single attribute value on an action.

    This is the preferred tool for setting action attributes — especially rich text values
    containing HTML. Each value is a simple top-level parameter, avoiding the nested
    JSON serialization issues that occur with update_action or update_actions.

    Call this once per attribute per action. Provide exactly one of: rich_text, choice_id, or text.

    Use get_plan to discover attribute type IDs, formats, and choice option IDs.
    """
    if ctx is None:
        raise ToolError('Context is required for write authorization.')
    await require_mcp_plan_write_authorization(plan_ref=plan_id, tool_name='update_action_attribute', ctx=ctx)

    value_kwargs: dict[str, Any] = {}
    provided = sum(x is not None for x in (rich_text, choice_id, text))
    if provided != 1:
        raise ToolError('Provide exactly one of: rich_text, choice_id, or text.')

    if rich_text is not None:
        value_kwargs['richText'] = rich_text
    elif choice_id is not None:
        value_kwargs['choice'] = AttributeValueChoiceInput(choiceId=choice_id)
    elif text is not None:
        value_kwargs['text'] = text

    attr_input = ActionAttributeUpdateInput(
        attributeTypeId=attribute_type_id,
        value=ActionAttributeValueInput(**value_kwargs),
    )

    result = await execute_operation(
        UpdateAction,
        UpdateAction.Arguments(
            planId=plan_id,  # type: ignore[call-arg]
            input=ActionUpdateInput(id=action_id, attributeValues=[attr_input]),
        ),
    )
    action = check_operation_result(result.action.update_action)
    return f"Updated attribute '{attribute_type_id}' on action {action.identifier} ({action.id})"


@register_tool(annotations=ToolAnnotations(title='Update multiple actions in a plan', idempotentHint=True))
async def update_actions(
    plan_id: Annotated[str, 'The ID (pk or identifier) of the plan to update the actions in'],
    actions: Annotated[list[ActionUpdateInput], 'List of updates to perform'],
    ctx: Context | None = None,
) -> str:
    """
    Bulk update multiple actions' core fields (description, categories, responsible parties, links).

    Updates only the fields provided in each action dict. Fields not included are left unchanged.
    For list fields (categories, responsible_parties, links), the provided list
    replaces the existing values.

    IMPORTANT: Do NOT include attribute values (rich text, choice, etc.) in this call.
    Use update_action_attribute instead for setting attributes — it accepts each value as
    a simple top-level parameter, which avoids serialization issues with nested JSON/HTML.

    Use list_actions to discover action IDs, and get_plan to find attribute type IDs and
    choice option IDs.
    """

    if ctx is None:
        raise ToolError('Context is required for write authorization.')
    await require_mcp_plan_write_authorization(plan_ref=plan_id, tool_name='update_actions', ctx=ctx)

    result = await execute_operation(
        UpdateActions,
        UpdateActions.Arguments(
            planId=plan_id,  # type: ignore[call-arg]
            actions=actions,
        ),
    )
    update_result = check_operation_result(result.action.update_actions)
    return f'Updated {update_result.count} actions (IDs: {", ".join(update_result.ids)})'


def register_action_tools(_mcp: FastMCP) -> None:
    """Register all action-related MCP tools."""
    pass
