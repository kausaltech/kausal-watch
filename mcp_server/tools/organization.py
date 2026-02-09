from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from mcp_server.__generated__.schema import MCPListOrganizations

from .helpers import execute_operation

if TYPE_CHECKING:
    from fastmcp import FastMCP


async def list_organizations(
    plan: Annotated[str | None, "Plan identifier to filter organizations by"] = None,
    parent: Annotated[str | None, "Parent organization ID to filter children"] = None,
    depth: Annotated[int | None, "Maximum depth in organization hierarchy to return"] = None,
    contains: Annotated[str | None, "Filter organizations by name substring"] = None,
) -> MCPListOrganizations:
    """
    List organizations with optional filtering.

    Filter by plan to get plan-related organizations, by parent to get children of a specific org,
    by depth to limit hierarchy traversal, or by name substring.
    """
    result = await execute_operation(
        MCPListOrganizations,
        MCPListOrganizations.Arguments(plan=plan, parent=parent, depth=depth, contains=contains),
    )  # type: ignore[type-var]

    return result


def register_organization_tools(mcp: FastMCP) -> None:
    """Register all organization-related MCP tools."""

    mcp.tool(list_organizations)
