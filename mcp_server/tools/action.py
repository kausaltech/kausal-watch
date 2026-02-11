from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastmcp.exceptions import ToolError

from mcp_server.__generated__.schema import (
    ActionAttributeValueInput,
    ActionInput,
    MCPCreateAction,
    MCPGetActions,
    MCPGetActionsAdminActions,
    MCPListActions,
)

from .helpers import execute_operation, execute_schema_query

if TYPE_CHECKING:
    from fastmcp import FastMCP


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
        MCPListActions,  # type: ignore[type-var]
        MCPListActions.Arguments(plan=plan, category=category, first=first, orderBy=order_by),
    )

    if result.plan_actions is None:
        raise ToolError(f"Plan '{plan}' not found or not accessible")

    lines: list[str] = []
    for action in result.plan_actions:
        parts = [f"{action.identifier} (id:{action.id}): {action.name}"]

        # Add status
        if action.status_summary:
            parts.append(f"[{action.status_summary.label}]")

        # Add primary org
        if action.primary_org:
            org_name = action.primary_org.abbreviation or action.primary_org.name
            parts.append(f"({org_name})")

        lines.append(" ".join(parts))

    return "\n".join(lines)


async def get_actions(
    ids: Annotated[list[str], 'List of action IDs to fetch'],
) -> list[MCPGetActionsAdminActions]:
    """
    Get detailed information about multiple actions by their IDs.

    Returns comprehensive action details including status, organizations,
    tasks, indicators, and more. Use list_actions to discover action IDs first.
    """
    result = await execute_operation(MCPGetActions, MCPGetActions.Arguments(ids=ids))  # type: ignore[type-var]
    return result.admin.actions


async def query_actions(
    plan: Annotated[str, "The plan identifier (e.g., 'sunnydale', 'bremen-klima-copy1')"],
    fields: Annotated[
        str,
        "GraphQL fields to select (fragment body on Action type). Read schema://action-fields for available fields.",
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
    query = """
    query MCPQueryActions($plan: ID!, $category: ID, $first: Int) @context(input: {identifier: $plan}) {
        planActions(plan: $plan, category: $category, first: $first) {
            ...FreeformActionFields
        }
    }
    fragment FreeformActionFields on Action {
        %s
    }
    """ % fields

    variables: dict[str, Any] = {'plan': plan}
    if category is not None:
        variables['category'] = category
    if first is not None:
        variables['first'] = first

    result = await execute_schema_query(query, variables)

    if result.errors:
        error_msgs = '; '.join(str(e) for e in result.errors)
        raise ToolError(f"GraphQL query failed: {error_msgs}")

    if result.data is None:
        raise ToolError("No data returned from query")

    return result.data.get('planActions', [])


async def create_action(
    plan_id: Annotated[str, "The ID (pk) of the plan to create the action in"],
    name: Annotated[str, "Name of the action"],
    identifier: Annotated[str | None, "Action identifier (required if plan has action identifiers enabled)"] = None,
    description: Annotated[str | None, "Detailed description of the action"] = None,
    primary_org_id: Annotated[str | None, "ID of the primary responsible organization"] = None,
    category_ids: Annotated[list[str] | None, "List of category IDs to assign to the action"] = None,
    attribute_values: Annotated[
        list[dict[str, str]] | None,
        "List of attribute values, each with 'attribute_type_id' and 'choice_id'",
    ] = None,
) -> MCPCreateAction:
    """
    Create a new action in a plan.

    Use get_plan to check if the plan requires action identifiers (hasActionIdentifiers feature).
    Use list_organizations to find organization IDs for primary_org_id.
    """
    attr_inputs: list[ActionAttributeValueInput] | None = None
    if attribute_values:
        attr_inputs = [
            ActionAttributeValueInput(
                attributeTypeId=av['attribute_type_id'],
                choiceId=av['choice_id'],
            )
            for av in attribute_values
        ]

    result = await execute_operation(
        MCPCreateAction,
        MCPCreateAction.Arguments(
            input=ActionInput(
                planId=plan_id,
                name=name,
                identifier=identifier or '',
                description=description,
                primaryOrgId=primary_org_id,
                categoryIds=category_ids,
                attributeValues=attr_inputs,
            )
        ),
    )  # type: ignore[type-var]

    return result


def register_action_tools(mcp: FastMCP) -> None:
    """Register all action-related MCP tools."""

    mcp.tool(list_actions)
    mcp.tool(get_actions)
    mcp.tool(query_actions)
    mcp.tool(create_action)
