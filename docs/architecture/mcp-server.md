# MCP Server Architecture

## Overview

Kausal Watch exposes an MCP (Model Context Protocol) server at `/mcp` to enable AI assistants (LibreChat, Claude.ai, etc.) to query climate action plan data.

## Architecture

- **Framework**: FastMCP with Streamable HTTP transport
- **Mounting**: Under `/mcp` in the Django ASGI app via `ProtocolTypeRouter`
- **Authentication**: OAuth2 Bearer tokens via existing `HTTPMiddleware`
- **Data Layer**: GraphQL queries executed programmatically, reusing all existing permission logic

## File Structure

```
mcp_server/
├── __init__.py              # Package init
├── server.py                # FastMCP app, resource & tool registration
├── queries.graphql          # GraphQL queries for MCP tools
├── mcp_client_tool.py       # CLI tool for testing
├── tools/                   # Tool implementations by domain
│   ├── __init__.py          # Exports register functions
│   ├── helpers.py           # Shared utilities (execute_operation, execute_schema_query)
│   ├── plan.py              # Plan-related tools (list_plans, get_plan)
│   ├── action.py            # Action-related tools (list_actions, get_actions, query_actions)
│   ├── organization.py      # Organization-related tools (list_organizations)
│   └── user.py              # User-related tools (user_details)
└── __generated__/           # Auto-generated GraphQL client code (DO NOT EDIT)
    └── schema.py            # Pydantic models for all operations
```

## Development Workflow

### Adding a New Tool

1. **Add the GraphQL query** to `mcp_server/queries.graphql`:

   ```graphql
   query MCPGetPlan($identifier: ID!) @context(input: {identifier: $identifier}) {
       plan(id: $identifier) {
           id
           identifier
           name
           shortName
           # ... other fields
       }
   }
   ```

   > **Note**: Use the `@context` directive on plan-specific queries to activate the
   > correct language and plan context. Pass the plan identifier via
   > `@context(input: {identifier: $planVariable})`.

2. **Regenerate the client code**:

   ```bash
   kausal_common/development/tools/generate-mcp-schema.sh
   ```

   This generates typed Pydantic models in `mcp_server/__generated__/schema.py`.

3. **Add the tool** to the appropriate file in `mcp_server/tools/`:

   ```python
   # In mcp_server/tools/plan.py
   from mcp_server.__generated__.schema import MCPGetPlan

   from .helpers import execute_operation

   async def get_plan(identifier: str) -> MCPGetPlan:
       """Get plan details by identifier."""
       result = await execute_operation(MCPGetPlan, MCPGetPlan.Arguments(identifier=identifier))
       if result.plan is None:
           raise ToolError(f"Plan '{identifier}' not found")
       return result
   ```

   Tools are organized by domain (e.g., `plan.py`, `action.py`, `indicator.py`).
   Each module exports a `register_*_tools(mcp)` function called from `server.py`.
   The tool schema is introspected through the function type annotations,
   so the types need to be available in runtime (not imported in a TYPE_CHECKING block).

   When constructing Input types from the generated schema, use the
   **camelCase** field names (matching the GraphQL schema), not the snake_case Python
   field names:

   ```python
   # Correct - use camelCase (the alias)
   input=AddRelatedOrganizationInput(planId=plan_id, organizationId=organization_id)

   # Wrong - snake_case will fail at runtime
   input=AddRelatedOrganizationInput(plan_id=plan_id, organization_id=organization_id)
   ```

   This is because the generated Pydantic models use `Field(alias='camelCase')`.
   Note: basedpyright LSP may show errors for this (it doesn't understand Pydantic
   aliases), but mypy with the Pydantic plugin handles it correctly.

## Testing

### Using the CLI Tool

The `mcp_client_tool.py` script provides a simple way to test the MCP server:

```bash
# List available tools
uv run mcp_server/mcp_client_tool.py --list-tools

# Call a tool
uv run mcp_server/mcp_client_tool.py --call list_plans

# Call with arguments
uv run mcp_server/mcp_client_tool.py --call hello_world --args '{"name": "World"}'

# Get raw JSON output
uv run mcp_server/mcp_client_tool.py --call list_plans --raw
```

**Prerequisites**: Set `MCP_CLIENT_TOKEN` in your `.env` file with a valid OAuth2 access token.

### Using MCP Inspector

1. Start the server: `uvicorn aplans.asgi:application --reload`
2. Open MCP Inspector and connect to `http://localhost:8000/mcp`
3. Add authorization header: `Authorization: Bearer <your-token>`

## Authentication Flow

1. Client sends `Authorization: Bearer <token>` header
2. `HTTPMiddleware` validates the token and sets `scope['user']`
3. `WatchGraphQLContext` reads the user from the ASGI scope
4. GraphQL resolvers use `info.context.user` for permission checks

## Tools

### Compact Output Formats

List tools return compact, token-efficient formats designed for AI consumption:

**`list_plans`** returns one line per plan:
```
sunnydale: Sunnydale Climate Action Plan (Climate) <City of Sunnydale [498]>
bremen-klima-copy1: Aktionsplan Klimaschutz... [2024] <Freie Hansestadt Bremen [123]>
```

**`list_actions`** returns one line per action with ID for follow-up queries:
```
U1 (id:1111): Climate impact assessment [Late] (Urban Planning)
U2 (id:1112): Reducing distances with dense urban planning [On time]
```

### Available Tools

| Tool | Description |
|------|-------------|
| `list_plans` | List accessible plans (compact format) |
| `get_plan` | Get plan details including attribute types and category types |
| `list_actions` | List/filter actions (compact format with IDs) |
| `get_actions` | Get full details for multiple actions by IDs |
| `query_actions` | Query actions with custom GraphQL field selection |
| `list_organizations` | List organizations, optionally filtered by plan |
| `user_details` | Get current user info |

### Flexible Queries with `query_actions`

The `query_actions` tool allows AI assistants to construct custom queries with specific
field selections. This is useful for analytical queries like "which high-impact actions
should I focus on now?"

**Workflow:**
1. Use `get_plan` to understand the plan's attribute schema
2. Read `schema://action-fields` resource for available Action fields
3. Use `query_actions` with only the fields needed for analysis

**Example - Find late actions with Senate priorities:**
```python
query_actions(
    plan="bremen-klima-copy1",
    fields="""
        identifier
        name
        statusSummary { label sentiment }
        attributes {
            ... on AttributeChoice {
                type { identifier name }
                choice { identifier name }
            }
        }
    """,
    first=20
)
```

This returns actions with their status and choice attributes (like "Handlungsschwerpunkt
des Senats"), allowing the AI to filter and prioritize in context.

## Resources

| URI | Description |
|-----|-------------|
| `schema://action-fields` | GraphQL fields available on Action type (from MCPGetActions query) |

## Planned Tools

| Tool | Description |
|------|-------------|
| `search` | Full-text search across actions and indicators |
| `list_indicators` | List indicators with optional filtering |
| `get_indicator` | Get indicator with historical values |
| `get_category_tree` | Hierarchical category structure |

## Future Considerations

- Write tools (update action status, add comments)
- Customer-facing deployment with plan-scoped tokens
- Additional MCP Resources for plans/actions
- MCP Prompts for common queries
- Generalize to `kausal_common` for Kausal Paths reuse
