# MCP Server Architecture

## Overview

Kausal Watch exposes an MCP (Model Context Protocol) server at `/mcp` to enable AI assistants (LibreChat, Claude.ai, etc.) to query climate action plan data.

## Architecture

- **Framework**: FastMCP with Streamable HTTP transport
- **Mounting**: Under `/mcp` in the Django ASGI app via `ProtocolTypeRouter`
- **Authentication**: OAuth2 Bearer tokens via existing `HTTPMiddleware`
- **Data Layer**: GraphQL queries and mutations executed programmatically, reusing all existing permission logic

## File Structure

```
mcp_server/
├── __init__.py              # Package init
├── server.py                # FastMCP app, resource & tool registration
├── queries.graphql          # GraphQL queries and mutations for MCP tools
├── generated_base.py        # Base models for generated code (QueryModel, MutationModel, ObjectBaseModel)
├── mcp_client_tool.py       # CLI tool for testing
├── tools/                   # Tool implementations by domain
│   ├── __init__.py          # Exports register functions
│   ├── helpers.py           # Shared utilities (execute_operation, check_operation_result)
│   ├── plan.py              # Plan tools (list/get/create/delete plans, category types, etc.)
│   ├── action.py            # Action tools (list/get/query/create actions)
│   ├── organization.py      # Organization tools (list/create organizations)
│   └── user.py              # User-related tools (user_details)
└── __generated__/           # Auto-generated GraphQL client code (DO NOT EDIT)
    └── schema.py            # Pydantic models for all operations
```

## Development Workflow

### Adding a Read Tool (Query)

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
   Query operations generate classes inheriting from `QueryModel`.

3. **Add the tool** to the appropriate file in `mcp_server/tools/`:

   ```python
   from mcp_server.__generated__.schema import MCPGetPlan

   from .helpers import execute_operation

   async def get_plan(identifier: str) -> MCPGetPlan:
       """Get plan details by identifier."""
       result = await execute_operation(MCPGetPlan, MCPGetPlan.Arguments(identifier=identifier))
       if result.plan is None:
           raise ToolError(f"Plan '{identifier}' not found")
       return result
   ```

### Adding a Write Tool (Mutation)

Write tools follow the same first two steps (add operation to `queries.graphql`,
regenerate). The key differences are in the GraphQL operation and the tool implementation.

1. **Add the GraphQL mutation** to `mcp_server/queries.graphql`.
   Mutations that can return validation errors use a union return type — include
   `...OpInfo` alongside the result fields:

   ```graphql
   mutation MCPCreateCategory($input: CategoryInput!) {
       plan {
           createCategory(input: $input) {
               ... on Category {
                   id
                   identifier
                   name
               }
               ...OpInfo
           }
       }
   }
   ```

   The `OpInfo` fragment is defined once in the file and captures `OperationInfo`
   messages (validation errors returned by `handle_django_errors`).

2. **Regenerate** as above. Mutation operations generate classes inheriting from
   `MutationModel`. The generated return type will be a union of the result model
   and `OpInfo`.

3. **Add the tool**, using `check_operation_result()` to unwrap the union:

   ```python
   from mcp_server.__generated__.schema import CreateCategory, CategoryInput, CategoryDetails

   from .helpers import check_operation_result, execute_operation

   async def create_category(
       type_id: Annotated[str, 'The ID of the category type'],
       identifier: Annotated[str, 'Unique identifier'],
       name: Annotated[str, 'Display name'],
   ) -> CategoryDetails:
       """Create a new category within a category type."""
       result = await execute_operation(
           CreateCategory,
           CreateCategory.Arguments(
               input=CategoryInput(typeId=type_id, identifier=identifier, name=name)
           ),
       )
       return check_operation_result(result.plan.create_category)
   ```

   `check_operation_result()` checks if the result is an `OpInfo` (i.e., the mutation
   returned validation errors instead of a result object) and raises a `ToolError`
   with the error messages. Otherwise it returns the unwrapped result.

### Common Conventions

Tools are organized by domain (e.g., `plan.py`, `action.py`, `organization.py`).
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

## GraphQL Mutation Conventions

The MCP write tools are backed by Strawberry GraphQL mutations defined in each app's
`mutations.py`. See also the testing conventions in `*/tests/test_graphql_mutations.py`.

### Mutation Structure

Mutations are grouped into `@sb.type` classes (e.g., `PlanMutations`, `ActionMutations`)
and decorated with `@gql.mutation()` from `aplans.gql`:

```python
from aplans import gql
from kausal_common.strawberry.permissions import SuperuserOnly

@sb.type
class PlanMutations:
    @gql.mutation(permission_classes=[SuperuserOnly], description='Create a new plan')
    def create_plan(self, info: gql.Info, input: PlanInput) -> PlanNode:
        ...
```

The `gql.mutation()` decorator wraps `strawberry_django.mutation` with:
- **`handle_django_errors=True`** — Django's `ValidationError` is automatically caught
  and transformed into `OperationInfo` messages (kind/message/field/code) instead of
  raising a GraphQL error. This means mutations return a union of the result type and
  `OperationInfo`.
- **`MutationExtension`** — wraps every mutation in `transaction.atomic()`, overrides
  the language to English (for consistent error messages), and converts lazy strings.

### Input Types

- `@strawberry_django.input(Model)` for model-backed inputs (fields use `auto`)
- `@sb.input` for custom input types not directly mapped to models

### Helper Functions (`aplans.gql`)

| Helper | Purpose |
|--------|---------|
| `gql.mutation()` | Mutation decorator with automatic transaction + error handling |
| `gql.parse_input()` | Convert Strawberry input object to dict |
| `gql.prepare_instance()` | Prepare a model instance from parsed data, handling M2M |
| `gql.prepare_create_update()` | `parse_input` + `prepare_instance` in one call |
| `gql.get_plan_or_error()` | Look up a plan by ID or identifier, or raise |
| `get_or_error()` | Generic get-or-raise with proper GraphQL error types |

### Testing Mutations

Mutation tests use helpers from `kausal_common`:

- **`OP_INFO_FRAGMENT`** (`kausal_common.strawberry.mutations`) — GraphQL fragment
  appended to mutation query strings to capture `OperationInfo` messages.
- **`assert_operation_errors()`** (`kausal_common.testing.graphql`) — asserts that a
  mutation result contains exactly the expected `OperationMessage`s and no result fields.
- **`graphql_client_query_data`** fixture — for success paths (asserts no errors,
  returns `data`).
- **`graphql_client_query`** fixture — for error/validation paths (returns full response
  including `errors`).

Test file structure:
1. Module-level `pytestmark = pytest.mark.django_db`
2. Mutation query strings as constants (with `+ OP_INFO_FRAGMENT`)
3. Permission test class (unauthenticated + non-superuser)
4. One test class per mutation with happy path, validation, and edge case tests

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

#### Read Tools

| Tool | Description |
|------|-------------|
| `list_plans` | List accessible plans (compact format) |
| `get_plan` | Get plan details including attribute types and category types |
| `list_actions` | List/filter actions (compact format with IDs) |
| `get_actions` | Get full details for multiple actions by IDs |
| `query_actions` | Query actions with custom GraphQL field selection |
| `list_organizations` | List organizations, optionally filtered by plan |
| `user_details` | Get current user info |

#### Write Tools

All write tools require superuser access unless noted otherwise.

| Tool | Description |
|------|-------------|
| `create_plan` | Create a new action plan |
| `delete_plan` | Delete a recently created plan (must be <2 days old) |
| `add_related_organization` | Add an organization to a plan (general admin) |
| `create_category_type` | Create a category type for a plan |
| `create_category` | Create a category within a category type |
| `create_attribute_type` | Create an attribute type for actions in a plan |
| `create_action` | Create a new action in a plan |
| `create_organization` | Create a new organization |

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
| `update_action` | Update action status, details, and metadata |

## Future Considerations

- Customer-facing deployment with plan-scoped tokens
- Additional MCP Resources for plans/actions
- MCP Prompts for common queries
- Generalize to `kausal_common` for Kausal Paths reuse
