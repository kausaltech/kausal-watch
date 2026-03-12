from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast, overload

from django.utils import timezone

from asgiref.sync import sync_to_async
from fastmcp.exceptions import ToolError
from mcp.server.elicitation import CancelledElicitation, DeclinedElicitation
from mcp.types import ToolAnnotations

from kausal_common.strawberry.views import get_base_context
from kausal_common.users import user_or_bust

from aplans.schema import schema
from aplans.schema_context import WatchGraphQLContext

from mcp_server.__generated__.schema import OpInfo

from ..generated_base import MutationModel, ObjectBaseModel, QueryModel

if TYPE_CHECKING:
    from pydantic import BaseModel
    from strawberry.types import ExecutionResult

    from fastmcp import Context
    from starlette.requests import Request as StarletteRequest

    from users.models import User


type ToolFunc = Callable[..., Awaitable[Any]]

READONLY_ANNOTATIONS = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

tool_registry: list[tuple[ToolFunc, ToolAnnotations | None]] = []
WRITE_AUTH_DURATION_CHOICES = ['15m', '1h', '8h', '24h']
WRITE_AUTH_DURATION_MAP: dict[str, timedelta] = {
    '15m': timedelta(minutes=15),
    '1h': timedelta(hours=1),
    '8h': timedelta(hours=8),
    '24h': timedelta(hours=24),
}

@overload
def register_tool[F: ToolFunc](func: F) -> F: ...

@overload
def register_tool[F: ToolFunc](*, annotations: ToolAnnotations | None = None) -> Callable[[F], F]: ...

def register_tool[F: ToolFunc](func: F | None = None, *, annotations: ToolAnnotations | None = None) -> F | Callable[[F], F]:
    def decorator(f: F) -> F:
        for existing_func, _ in tool_registry:
            if existing_func is f:
                raise ValueError(f"Tool {f.__name__} already registered")
        tool_registry.append((f, annotations))
        return f

    if func is not None:
        return decorator(func)
    return decorator


def get_schema_execution_context():
    from mcp.server.lowlevel.server import request_ctx

    context = request_ctx.get()
    req = cast('StarletteRequest', context.request)
    base_ctx = get_base_context(req, None)
    schema_ctx = WatchGraphQLContext(**base_ctx)
    return schema_ctx


def resolve_current_user() -> User:
    schema_ctx = get_schema_execution_context()
    return user_or_bust(schema_ctx.user)


async def resolve_plan_by_id_or_identifier(plan_ref: str):
    from actions.models import Plan

    user = resolve_current_user()
    plan = await sync_to_async(lambda: Plan.objects.qs.visible_for_user(user).by_id_or_identifier(plan_ref).first())()
    if plan is None:
        raise ToolError(f"Plan '{plan_ref}' not found or not accessible")
    return plan


async def resolve_plan_ref_from_category_type(type_id: str) -> str:
    from actions.models import CategoryType

    category_type = await sync_to_async(lambda: CategoryType.objects.filter(pk=type_id).select_related('plan').first())()
    if category_type is None:
        raise ToolError(f"Category type '{type_id}' not found")
    return str(category_type.plan.pk)


async def _persist_write_authorization_grant(plan_ref: str, granted_by_tool: str, duration_key: str) -> tuple[Any, Any]:
    from users.models import MCPPlanWriteAuthorizationGrant

    user = resolve_current_user()
    plan = await resolve_plan_by_id_or_identifier(plan_ref)
    now = timezone.now()
    expires_at = now + WRITE_AUTH_DURATION_MAP[duration_key]
    await sync_to_async(MCPPlanWriteAuthorizationGrant.objects.update_or_create)(
        user=user,
        plan=plan,
        defaults={
            'expires_at': expires_at,
            'granted_by_tool': granted_by_tool,
            'granted_at': now,
        },
    )
    return plan, expires_at


async def _has_active_write_authorization_grant(plan_ref: str) -> bool:
    from users.models import MCPPlanWriteAuthorizationGrant

    user = resolve_current_user()
    plan = await resolve_plan_by_id_or_identifier(plan_ref)
    grant = await sync_to_async(lambda: MCPPlanWriteAuthorizationGrant.objects.filter(user=user, plan=plan).first())()
    if grant is None:
        return False
    return grant.is_active()


async def require_mcp_plan_write_authorization(plan_ref: str, tool_name: str, ctx: Context) -> None:
    if await _has_active_write_authorization_grant(plan_ref):
        return

    plan = await resolve_plan_by_id_or_identifier(plan_ref)
    response = await ctx.elicit(
        (
            f"Authorize write access for plan {plan.name} ({plan.identifier}) using tool '{tool_name}'. "
            "Choose how long this authorization should remain valid."
        ),
        WRITE_AUTH_DURATION_CHOICES,  # type: ignore[arg-type]
    )
    if isinstance(response, (DeclinedElicitation, CancelledElicitation)):
        raise ToolError(f"Write authorization for plan '{plan.identifier}' was not granted.")

    duration_key = response.data
    if duration_key not in WRITE_AUTH_DURATION_MAP:
        raise ToolError(f'Invalid authorization duration: {duration_key}')
    await _persist_write_authorization_grant(plan_ref=plan_ref, granted_by_tool=tool_name, duration_key=duration_key)  # type: ignore[arg-type]


async def authorize_mcp_plan_write_access(plan_ref: str, duration_key: str, granted_by_tool: str) -> str:
    plan, expires_at = await _persist_write_authorization_grant(
        plan_ref=plan_ref,
        granted_by_tool=granted_by_tool,
        duration_key=duration_key,
    )
    return (
        f"Write access authorized for plan '{plan.identifier}' until "
        f'{timezone.localtime(expires_at).isoformat()}.'
    )


async def execute_schema_query(query: str, variables: dict[str, Any] | None = None) -> ExecutionResult:
    schema_ctx = get_schema_execution_context()
    res = await sync_to_async(schema.execute_sync)(query, context_value=schema_ctx, variable_values=variables)
    return res


async def execute_operation[T: QueryModel | MutationModel](operation_class: type[T], args: BaseModel | None = None) -> T:
    """
    Execute a turms-generated GraphQL operation and return the validated result.

    Args:
        operation_class: A turms-generated Pydantic model with Meta.document and Arguments inner classes.
        args: The arguments to pass to the operation.

    Returns:
        The validated operation result as an instance of the operation class.

    Raises:
        RuntimeError: If the GraphQL execution returns errors.

    """
    # Build the arguments and serialize to dict
    if args is None:
        variables_dict = {}
    else:
        assert isinstance(args, operation_class.Arguments)
        variables_dict = args.model_dump(by_alias=True, exclude_none=True)

    # Execute the query
    result = await execute_schema_query(
        query=operation_class.Meta.document,
        variables=variables_dict,
    )

    if result.errors:
        error_msgs = '; '.join(str(e) for e in result.errors)
        msg = f"GraphQL errors: {error_msgs}"
        raise RuntimeError(msg)

    # Validate and return the result
    return cast('T', operation_class.model_validate(result.data))


def check_operation_result[ResT: ObjectBaseModel | None](result: ResT | OpInfo) -> ResT:
    if isinstance(result, OpInfo):
        msg_str = '\n'.join(msg.message for msg in result.messages)
        raise ToolError('Tool call failed:\n' + msg_str)
    return result
