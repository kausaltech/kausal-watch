from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
from contextlib import ExitStack, contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import translation
from graphene_django.views import GraphQLView
from graphql import ExecutionContext
from graphql.error import GraphQLError
from graphql.language.ast import StringValueNode, VariableNode
from graphql.type import GraphQLResolveInfo
from rest_framework.authentication import TokenAuthentication

import sentry_sdk
from loguru import logger
from rich.console import Console
from rich.syntax import Syntax
from sentry_sdk import tracing as sentry_tracing

from kausal_common.deployment import env_bool

from aplans.types import WatchAPIRequest

from actions.models import Plan
from users.models import User

from .graphql_helpers import GraphQLAuthFailedError, GraphQLAuthRequiredError
from .graphql_types import WorkflowStateEnum

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator, Iterable

    from graphql import DirectiveNode, ExecutionResult, GraphQLResolveInfo
    from rest_framework.authentication import TokenAuthentication

    from aplans.types import WatchAPIRequest

    from actions.models.plan import PlanQuerySet


SUPPORTED_LANGUAGES = {x[0].lower() for x in settings.LANGUAGES}

PLAN_IDENTIFIER_HEADER = 'x-cache-plan-identifier'
PLAN_DOMAIN_HEADER = 'x-cache-plan-domain'
WILDCARD_DOMAIN_HEADER = 'x-wildcard-domains'


class APITokenMiddleware:
    # def authenticate_user(self, info):
    #     raise GraphQLError('Token not found')

    def process_auth_directive(self, info: GraphQLResolveInfo, directive: DirectiveNode):  # noqa: C901, PLR0912
        user = None
        token = None
        variable_vals = info.variable_values
        for arg in directive.arguments:
            if arg.name.value == 'uuid':
                if isinstance(arg.value, VariableNode):
                    val = variable_vals.get(arg.value.name.value)
                else:
                    if not isinstance(arg.value, StringValueNode):
                        raise GraphQLError("Invalid type: %s" % str(type(arg.value)), [arg])
                    val = arg.value.value
                try:
                    user = User.objects.get(uuid=UUID(val))
                except User.DoesNotExist as e:
                    raise GraphQLAuthFailedError("User not found", [arg]) from e
                except (ValidationError, ValueError, TypeError) as e:
                    raise GraphQLAuthFailedError("Invalid UUID", [arg]) from e

            elif arg.name.value == 'token':
                if isinstance(arg.value, VariableNode):
                    val = variable_vals.get(arg.value.name.value)
                else:
                    if not isinstance(arg.value, StringValueNode):
                        raise GraphQLError("Invalid type: %s" % str(type(arg.value)), [arg])
                    val = arg.value.value
                token = val

        if not token:
            raise GraphQLAuthFailedError("Token required", [directive])
        if not user:
            raise GraphQLAuthFailedError("User required", [directive])

        try:
            if user.auth_token.key != token:
                raise GraphQLAuthFailedError("Invalid token", [directive])
        except User.auth_token.RelatedObjectDoesNotExist:  # type: ignore
            raise GraphQLAuthFailedError("Invalid token", [directive]) from None

        info.context.user = user

    def resolve(self, next, root, info: GraphQLResolveInfo, **kwargs):
        if root is None:
            operation = info.operation
            for directive in operation.directives:
                if directive.name.value == 'auth':
                    self.process_auth_directive(info, directive)

        ret = next(root, info, **kwargs)
        return ret


class WorkflowStateMiddleware:
    def process_workflow_directive(self, info, directive):
        user = info.context.user
        if not user.is_authenticated:
            return WorkflowStateEnum.PUBLISHED
        variable_vals = info.variable_values
        for arg in directive.arguments:
            if arg.name.value == 'state':
                if isinstance(arg.value, VariableNode):
                    str_val =  variable_vals.get(arg.value.name.value)
                else:
                    str_val = arg.value.value
                return WorkflowStateEnum(str_val)
        return None

    def resolve(self, next, root, info, **kwargs):
        if root is None:
            operation = info.operation
            for directive in operation.directives:
                if directive.name.value == 'workflow':
                    info.context.watch_cache.query_workflow_state = self.process_workflow_directive(info, directive)

        return next(root, info, **kwargs)


class LocaleMiddleware:
    def process_locale_directive(self, info, directive):
        variable_vals = info.variable_values
        for arg in directive.arguments:
            if arg.name.value == 'lang':
                if isinstance(arg.value, VariableNode):
                    lang = variable_vals.get(arg.value.name.value)
                else:
                    lang = arg.value.value
                if lang.lower() not in SUPPORTED_LANGUAGES:
                    raise GraphQLError("unsupported language: %s" % lang)
                info.context.graphql_query_language = lang
                return lang
        return None

    def resolve(self, next, root, info, **kwargs):
        if root is None:
            info.context.graphql_query_language = None
            operation = info.operation
            lang = translation.get_language()
            for directive in operation.directives:
                if directive.name.value == 'locale':
                    lang = self.process_locale_directive(info, directive)
                    if lang is not None:
                        translation.activate(lang)
                        break
            else:
                # No locale directive found. Need to activate some language, otherwise this request would be served
                # using whatever language had been set while handling the previous request in the current thread.
                assert settings.LANGUAGE_CODE.lower() in SUPPORTED_LANGUAGES
                translation.activate(settings.LANGUAGE_CODE)
        return next(root, info, **kwargs)


IDTokenAuthentication: type[TokenAuthentication] | None = None
if importlib.util.find_spec('kausal_watch_extensions') is not None:
    from kausal_watch_extensions.auth.authentication import IDTokenAuthentication
    id_token_authentication_found = True


def perform_auth(request):
    if IDTokenAuthentication is None:
        return
    auth = IDTokenAuthentication()
    ret = auth.authenticate(request)
    if ret is not None:
        user, token = ret
        request.user = user


class WatchExecutionContext(ExecutionContext):
    def complete_value(self, return_type, field_nodes, info, path, result: Any) -> Awaitable[Any] | Any:
        if env_bool('TRACE_GRAPHQL_REQUESTS', default=False):
            import viztracer
            tracer = viztracer.get_tracer()
            if tracer is not None:
                with tracer.log_event('complete_value: %s' % ','.join(str(x) for x in path.as_list())):
                    return super().complete_value(return_type, field_nodes, info, path, result)
        return super().complete_value(return_type, field_nodes, info, path, result)


class SentryGraphQLView(GraphQLView):
    graphiql_version = "2.0.7"
    graphiql_sri = "sha256-qQ6pw7LwTLC+GfzN+cJsYXfVWRKH9O5o7+5H96gTJhQ="
    graphiql_css_sri = "sha256-gQryfbGYeYFxnJYnfPStPYFt0+uv8RP8Dm++eh00G9c="
    execution_context_class = WatchExecutionContext

    def __init__(self, *args, **kwargs):
        if 'middleware' not in kwargs:
            middleware = (APITokenMiddleware, WorkflowStateMiddleware, LocaleMiddleware)
            kwargs['middleware'] = middleware
        super().__init__(*args, **kwargs)

    def get_cache_key(self, request: WatchAPIRequest, data, query, variables):
        plan_identifier = request.headers.get(PLAN_IDENTIFIER_HEADER)
        plan_domain = request.headers.get(PLAN_DOMAIN_HEADER)
        if not plan_identifier and not plan_domain:
            logger.info('Skipping cache; required HTTP headers missing')
            return None

        qs: PlanQuerySet = Plan.objects.get_queryset()
        if plan_identifier:
            qs = qs.filter(identifier=plan_identifier)
        if plan_domain:
            qs = qs.for_hostname(plan_domain, request=request)
        plan = qs.first()
        if plan is None:
            logger.info('Skipping cache; no plan found')
            return None

        m = hashlib.sha1(usedforsecurity=False)
        m.update(os.getenv('BUILD_ID', 'dev').encode('utf8'))
        m.update(plan.cache_invalidated_at.isoformat().encode('utf8'))
        m.update(json.dumps(variables).encode('utf8'))
        m.update(query.encode('utf8'))
        key = m.hexdigest()
        return key

    def get_from_cache(self, key):
        return cache.get(key)

    def store_to_cache(self, key, result):
        return cache.set(key, result, timeout=600)

    def _enter_viztracer_stack(self, stack: ExitStack, operation_name: str) -> None:
        from django.db import connection

        from viztracer import VizTracer  # type: ignore

        def trace_sql_query(execute: Callable, sql: str, params: Iterable[Any], many: bool, context: dict) -> Any:
            with tracer.log_event('sql_query'):
                res = execute(sql, params, many, context)
            return res

        now_ts = datetime.now().strftime('%Y%m%d_%H%M%S')  # noqa: DTZ005
        Path('perf-traces').mkdir(exist_ok=True)
        trace_fn = f'perf-traces/{operation_name}_{now_ts}.json'
        tracer = VizTracer(output_file=trace_fn, max_stack_depth=15, log_async=True, tracer_entries=3000000)
        stack.enter_context(tracer)
        stack.enter_context(connection.execute_wrapper(trace_sql_query))
        logger.info(f'Saving trace to {trace_fn}')

    @contextmanager
    def measure_operation(self, operation_name: str) -> Generator[None]:
        perf_trace = env_bool('TRACE_GRAPHQL_REQUESTS', default=False)
        with ExitStack() as stack:
            if perf_trace:
                self._enter_viztracer_stack(stack, operation_name)
            yield

    def caching_execute_graphql_request(
            self, span, request: WatchAPIRequest, data, query, variables, operation_name, *args, **kwargs,
        ) -> ExecutionResult:
        key = self.get_cache_key(request, data, query, variables)
        span.set_tag('cache_key', key)
        if key:
            result = self.get_from_cache(key)
            if result is not None:
                span.set_tag('cache', 'hit')
                return result

        span.set_tag('cache', 'miss')
        with self.measure_operation(operation_name):
            result = super().execute_graphql_request(request, data, query, variables, operation_name, *args, **kwargs)
        if key and not result.errors:
            self.store_to_cache(key, result)

        return result

    def log_request(self, request: WatchAPIRequest, query, variables, operation_name):
        logger.info('GraphQL request %s from %s' % (operation_name, request._referer))
        debug_logging = settings.LOG_GRAPHQL_QUERIES
        if not debug_logging or not query:
            return
        console = Console()
        syntax = Syntax(query, "graphql")
        console.print(syntax)
        if variables:
            console.print('# Variables:')
            console.print(
                json.dumps(variables, indent=4, ensure_ascii=False),
            )

    def execute_graphql_request(self, request: WatchAPIRequest, data, query, variables, operation_name, *args, **kwargs):  # type: ignore[override]  # noqa: C901, PLR0915
        """Execute GraphQL request, cache results and send exceptions to Sentry."""
        request._referer = self.request.META.get('HTTP_REFERER')
        transaction: sentry_tracing.Transaction | None = sentry_sdk.get_current_scope().transaction

        wildcard_domains = request.headers.get(WILDCARD_DOMAIN_HEADER)
        request.wildcard_domains = [d.lower() for d in wildcard_domains.split(',')] if wildcard_domains else None

        log_context: dict[str, Any] = {}
        tenant_id = request.headers.get(PLAN_IDENTIFIER_HEADER)
        if tenant_id:
            log_context['tenant'] = tenant_id
        if operation_name:
            log_context['graphql_operation'] = operation_name
        if request.wildcard_domains:
            log_context['wildcard_domains'] = request.wildcard_domains

        with sentry_sdk.isolation_scope() as scope, logger.contextualize(**log_context):
            perform_auth(request)
            self.log_request(request, query, variables, operation_name)
            scope.set_context('graphql_variables', variables)
            scope.set_tag('graphql_operation_name', operation_name)
            scope.set_tag('referer', request._referer)

            if transaction is not None:
                span = transaction.start_child(op='graphql query', description=operation_name)
                span.set_data('graphql_variables', variables)
                span.set_tag('graphql_operation_name', operation_name)
                span.set_tag('referer', request._referer)
            else:
                # No tracing activated, use an inert Span
                span = sentry_tracing.Span()

            with span:
                wildcard_domains = request.headers.get(WILDCARD_DOMAIN_HEADER)
                request.wildcard_domains = [d.lower() for d in wildcard_domains.split(',')] if wildcard_domains else None
                if request.user and request.user.is_authenticated:
                    # Uncached execution for authenticated requests
                    with self.measure_operation(operation_name):
                        result = super().execute_graphql_request(request, data, query, variables, operation_name, *args, **kwargs)
                else:
                    result = self.caching_execute_graphql_request(
                        span, request, data, query, variables, operation_name, *args, **kwargs,
                    )
            # If 'invalid' is set, it's a bad request
            if result and result.errors:
                if settings.DEBUG:
                    from rich.traceback import Traceback
                    console = Console()

                    def print_error(err: GraphQLError) -> None:
                        console.print(err)
                        oe = err.original_error
                        if oe:
                            tb = Traceback.from_exception(
                                type(oe), oe, traceback=oe.__traceback__,
                            )
                            console.print(tb)
                else:
                    def print_error(err: GraphQLError) -> None:
                        pass

                for error in result.errors:
                    print_error(error)
                    err = error.original_error
                    if not err:
                        # It's an invalid query
                        continue
                    sentry_sdk.capture_exception(err)
        return result
