from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastmcp.exceptions import ToolError

from mcp_server.__generated__.schema import (
    AddRelatedOrganizationInput,
    MCPAddRelatedOrganization,
    MCPGetPlan,
    MCPListPlans,
)

from .helpers import execute_operation

if TYPE_CHECKING:
    from fastmcp import FastMCP


async def list_plans() -> str:
    """
    List accessible plans.

    Returns a compact list of plans with identifier, name, and the owner organization and id.
    Use get_plan(identifier) for full details on a specific plan.
    """
    result = await execute_operation(MCPListPlans, MCPListPlans.Arguments())  # type: ignore[type-var]
    if result.plans is None:
        raise ToolError("No plans found")

    lines: list[str] = []
    for plan in result.plans:
        name = plan.name
        if plan.short_name and plan.short_name != plan.name:
            name = f"{plan.name} ({plan.short_name})"
        if plan.version_name:
            name = f"{name} [{plan.version_name}]"
        owner_org = plan.organization
        lines.append(f"{plan.identifier}: {name} <{owner_org.name} [{owner_org.id}]>")

    return "\n".join(lines)


async def get_plan(
    identifier: Annotated[str, "The unique identifier of the plan (e.g., 'sunnydale', 'tampere-ilmasto')"],
) -> MCPGetPlan:
    """Get detailed information about a specific action plan."""
    result = await execute_operation(MCPGetPlan, MCPGetPlan.Arguments(identifier=identifier))  # type: ignore[type-var]

    if result.plan is None:
        raise ToolError(f"Plan '{identifier}' not found")

    return result


async def add_related_organization(
    plan_id: Annotated[str, "The ID (pk) or identifier of the plan to add the organization to"],
    organization_id: Annotated[str, "The ID of the organization to add as a related organization"],
) -> MCPAddRelatedOrganization:
    """
    Add a related organization to a plan.

    This is useful for fixing orphaned organization hierarchies where child organizations are related to a plan but
    their parent is not.
    """
    result = await execute_operation(
        MCPAddRelatedOrganization,
        MCPAddRelatedOrganization.Arguments(
            input=AddRelatedOrganizationInput(planId=plan_id, organizationId=organization_id)
        ),
    )  # type: ignore[type-var]

    if result.plan is None:
        raise ToolError("Failed to add related organization")

    return result


def register_plan_tools(mcp: FastMCP) -> None:
    """Register all plan-related MCP tools."""

    mcp.tool(list_plans)
    mcp.tool(get_plan)
    mcp.tool(add_related_organization)
