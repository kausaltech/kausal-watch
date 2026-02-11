from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastmcp.exceptions import ToolError

from mcp_server.__generated__.schema import MCPCreateOrganization, MCPListOrganizations, OrganizationInput

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


async def create_organization(
    name: Annotated[str, "The official name of the organization"],
    abbreviation: Annotated[str | None, "Short abbreviation (e.g. 'NASA', 'YM')"] = None,
    parent_id: Annotated[str | None, "ID of the parent organization. Omit for a root organization."] = None,
) -> MCPCreateOrganization:
    """
    Create a new organization.

    Organizations can be nested hierarchically. Use list_organizations to find parent IDs.
    """
    result = await execute_operation(
        MCPCreateOrganization,
        MCPCreateOrganization.Arguments(
            input=OrganizationInput(name=name, abbreviation=abbreviation, parentId=parent_id)
        ),
    )  # type: ignore[type-var]

    if result.organization is None:
        raise ToolError("Failed to create organization")

    return result


def register_organization_tools(mcp: FastMCP) -> None:
    """Register all organization-related MCP tools."""

    mcp.tool(list_organizations)
    mcp.tool(create_organization)
