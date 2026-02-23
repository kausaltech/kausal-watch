from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp.exceptions import ToolError

from mcp_server.__generated__.schema import UserDetails

from .helpers import execute_operation

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from mcp_server.__generated__.schema import UserDetailsMe


async def user_details() -> UserDetailsMe:
    """
    Get details about the currently authenticated user.

    Returns the user's ID, email, name, and superuser status.
    """
    result = await execute_operation(UserDetails, UserDetails.Arguments())

    if result.me is None:
        raise ToolError("Not authenticated or user not found")

    return result.me


def register_user_tools(mcp: FastMCP) -> None:
    """Register all user-related MCP tools."""

    mcp.tool(user_details)
