from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from mcp_server.__generated__.schema import CreateOrganization, ListOrganizations, OrganizationInput

from .helpers import check_operation_result, execute_operation

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from mcp_server.__generated__.schema import OrganizationBrief


async def list_organizations(
    plan: Annotated[str | None, "Plan identifier to filter organizations by"] = None,
    parent: Annotated[str | None, "Parent organization ID to filter children"] = None,
    depth: Annotated[int | None, "Maximum depth in organization hierarchy to return"] = None,
    contains: Annotated[str | None, "Filter organizations by name substring"] = None,
) -> ListOrganizations:
    """
    List organizations with optional filtering.

    Filter by plan to get plan-related organizations, by parent to get children of a specific org,
    by depth to limit hierarchy traversal, or by name substring.
    """
    result = await execute_operation(
        ListOrganizations,
        ListOrganizations.Arguments(plan=plan, parent=parent, depth=depth, contains=contains),
    )

    return result


async def create_organization(
    name: Annotated[str, "The official name of the organization"],
    abbreviation: Annotated[str | None, "Short abbreviation (e.g. 'NASA', 'YM')"] = None,
    parent_id: Annotated[str | None, "ID of the parent organization. Omit for a root organization."] = None,
    primary_language: Annotated[str, "Primary language code (ISO 639-1, e.g. 'en-US', 'fi', 'de-CH')"] = 'en-US',
) -> OrganizationBrief:
    """
    Create a new organization.

    Organizations can be nested hierarchically. Use list_organizations to find parent IDs.
    """
    result = await execute_operation(
        CreateOrganization,
        CreateOrganization.Arguments(
            input=OrganizationInput(name=name, abbreviation=abbreviation, parentId=parent_id, primaryLanguage=primary_language)
        ),
    )

    return check_operation_result(result.organization.create_organization)


def register_organization_tools(mcp: FastMCP) -> None:
    """Register all organization-related MCP tools."""

    mcp.tool(list_organizations)
    mcp.tool(create_organization)
