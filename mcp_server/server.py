from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from kausal_common.deployment import get_deployment_build_id

from .tools import register_action_tools, register_organization_tools, register_plan_tools, register_user_tools

# Create FastMCP without built-in auth - we handle auth ourselves via MCPAuthMiddleware
mcp = FastMCP(
    name='KausalWatch',
    instructions="""
        Provides tools for accessing and modifying action plans, indicators, and other
        related objects on the Kausal Watch platform.
    """,
    version=get_deployment_build_id() or '0.1.0-dev',
)

# Register tools from separate modules
register_plan_tools(mcp)
register_action_tools(mcp)
register_organization_tools(mcp)
register_user_tools(mcp)


# Register resources
@mcp.resource('schema://action-fields', description='GraphQL fields available on Action type for use with query_actions')
def get_action_fields_schema() -> str:
    """Return the Action fields from MCPGetActions as a schema reference."""
    from mcp_server.__generated__.schema import MCPGetActions

    return MCPGetActions.Meta.document


@mcp.resource(
    uri='file:///instructions/plan-metadata.md',
    description='Description of the plan metadata. Read this before using modify/create tools.',
    mime_type='text/markdown',
)
def get_plan_metadata_instructions() -> str:
    with Path('./docs/architecture/plan-metadata.md').open('r') as file:
        return file.read()
