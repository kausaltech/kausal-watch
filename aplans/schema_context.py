from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast
from typing_extensions import deprecated

from django.conf import settings
from django.utils import translation
from graphql import VariableNode, get_argument_values
from graphql.error import GraphQLError
from strawberry.utils.operation import get_first_operation

import sentry_sdk
from loguru import logger

from kausal_common.debugging.perf import ModelCreationCounter
from kausal_common.deployment import env_bool
from kausal_common.i18n.helpers import get_default_language
from kausal_common.strawberry.context import GraphQLContext
from kausal_common.strawberry.extensions import AuthenticationExtension, ExecutionCacheExtension, SchemaExtension
from kausal_common.users import user_or_none

from aplans.graphene_views import PLAN_DOMAIN_HEADER, PLAN_IDENTIFIER_HEADER

from actions.models import Plan

from .cache import PlanSpecificCache, WatchObjectCache

if TYPE_CHECKING:
    from collections.abc import Generator
    from contextlib import AbstractContextManager

    from graphql.language import DirectiveNode, OperationDefinitionNode

    from actions.models.plan import PlanQuerySet

logger = logger.bind(markup=True)

SUPPORTED_LANGUAGES = {x[0].lower() for x in settings.LANGUAGES}


def _arg_value(arg, variable_vals) -> Any:
    if isinstance(arg.value, VariableNode):
        return variable_vals.get(arg.value.name.value)
    return arg.value.value


@dataclass
class WatchGraphQLContext(GraphQLContext):
    request_plan: Plan | None = field(init=False)
    """The plan that was given as context in the GraphQL request."""

    cache: WatchObjectCache = field(init=False)
    _admin_cache: PlanSpecificCache | None = field(init=False, default=None)
    _plan_hostname: str | None = None
    active_plan: Plan | None = None

    def __post_init__(self):
        super().__post_init__()
        user = user_or_none(self.get_user())
        self.cache = WatchObjectCache(user=user)
        self.request_plan = None

    @property
    @deprecated('Use .cache instead')
    def watch_cache(self) -> WatchObjectCache:
        return self.cache

    @property
    def admin_cache(self) -> PlanSpecificCache:
        if self.active_plan is None:
            raise ValueError('Plan is not set')
        if self._admin_cache is None:
            self._admin_cache = self.cache.for_plan(self.active_plan)
        elif self._admin_cache.plan != self.active_plan:
            self._admin_cache = self.cache.for_plan(self.active_plan)
        return self._admin_cache


class WatchSchemaExtension(SchemaExtension[WatchGraphQLContext]):
    context_class: type[WatchGraphQLContext] = WatchGraphQLContext


class DeterminePlanContextExtension(WatchSchemaExtension):
    def process_locale_directive(self, directive: DirectiveNode) -> str:
        from kausal_common.strawberry.schema import locale_directive

        assert locale_directive.graphql_name is not None
        exec_ctx = self.execution_context
        directive_ast = exec_ctx.schema._schema.get_directive(locale_directive.graphql_name)
        assert directive_ast is not None
        lang = get_argument_values(directive_ast, directive, exec_ctx.variables).get('lang')
        if lang is None:
            raise GraphQLError('Locale directive missing lang argument', directive)
        lang = lang.lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise GraphQLError('unsupported language: %s' % lang, directive)
        return lang

    def get_plan_queryset(self) -> PlanQuerySet:
        return Plan.objects.get_queryset()

    def get_plan_by_identifier(
        self,
        queryset: PlanQuerySet,
        identifier: str,
        directive: DirectiveNode | None = None,
    ) -> Plan:
        try:
            if identifier.isnumeric():
                instance = queryset.get(id=identifier)
            else:
                instance = queryset.get(identifier=identifier)
        except Plan.DoesNotExist:
            raise GraphQLError('Plan with identifier %s not found' % identifier, directive) from None
        return instance

    def get_plan_by_hostname(
        self,
        queryset: PlanQuerySet,
        hostname: str,
        directive: DirectiveNode | None = None,
    ) -> Plan:
        try:
            instance = queryset.for_hostname(hostname).get()
        except Plan.DoesNotExist:
            logger.warning(f'No plan found for hostname {hostname}')
            raise GraphQLError('Plan matching hostname %s not found' % hostname, directive) from None
        return instance

    def process_instance_directive(self, directive: DirectiveNode) -> Plan:
        qs = self.get_plan_queryset()
        exec_ctx = self.execution_context
        arguments = {arg.name.value: _arg_value(arg, exec_ctx.variables) for arg in directive.arguments}
        identifier = arguments.get('identifier')
        hostname = arguments.get('hostname')
        _token = arguments.get('token')
        if identifier:
            return self.get_plan_by_identifier(qs, identifier, directive)
        if hostname:
            return self.get_plan_by_hostname(qs, hostname, directive)
        raise GraphQLError('Invalid plan directive', directive)

    def process_context_directive(self, directive: DirectiveNode) -> tuple[Plan | None, str | None]:
        from .schema import context_directive

        assert context_directive.graphql_name is not None
        exec_ctx = self.execution_context
        directive_ast = exec_ctx.schema._schema.get_directive(context_directive.graphql_name)
        assert directive_ast is not None
        ctx = get_argument_values(directive_ast, directive, exec_ctx.variables).get('input')
        if ctx is None:
            return None, None

        # FIXME: Filter by user permissions
        qs = self.get_plan_queryset()
        identifier = ctx.get('identifier')
        hostname = ctx.get('hostname')
        if identifier:
            plan = self.get_plan_by_identifier(qs, identifier)
        elif hostname:
            plan = self.get_plan_by_hostname(qs, hostname)
        else:
            return None, None
        locale = ctx.get('locale')
        if not locale:
            locale = plan.primary_language
        elif locale not in (plan.primary_language, *plan.other_languages):
            raise GraphQLError('unsupported language: %s' % locale, directive)
        return plan, locale

    def process_instance_headers(self) -> Plan | None:
        headers = self.get_request_headers()
        identifier = headers.get(PLAN_IDENTIFIER_HEADER)
        hostname = headers.get(PLAN_DOMAIN_HEADER)

        qs = self.get_plan_queryset()
        if identifier:
            return self.get_plan_by_identifier(qs, identifier)
        if hostname:
            return self.get_plan_by_hostname(qs, hostname)
        return None

    def determine_plan_and_locale(self, operation: OperationDefinitionNode) -> tuple[Plan | None, str | None]:
        plan: Plan | None = None
        locale: str | None = None

        for directive in operation.directives or []:
            directive_name = directive.name.value
            if directive_name == 'context':
                plan, locale = self.process_context_directive(directive)
                if plan is not None:
                    break
            elif directive_name == 'instance':
                plan = self.process_instance_directive(directive)
                break
        else:
            plan = self.process_instance_headers()

        if locale is None:
            for directive in operation.directives or []:
                directive_name = directive.name.value
                if directive_name != 'locale':
                    continue
                locale = self.process_locale_directive(directive)
                break
            else:
                if plan is not None:
                    locale = plan.primary_language

        if locale is None:
            locale = get_default_language()

        ctx = self.get_context()
        ctx.graphql_query_language = locale
        ctx.request_plan = plan
        return plan, locale

    def on_execute(self) -> Generator[None]:
        doc = self.execution_context.graphql_document
        if doc:
            op = get_first_operation(doc)
        else:
            op = None

        if not op or self.execution_context.result:
            yield
            return

        self.determine_plan_and_locale(op)
        yield


class ActivatePlanContextExtension(WatchSchemaExtension):
    def activate_language(self, lang: str):
        return cast('AbstractContextManager[Any]', translation.override(lang))

    def set_instance_scope(self) -> None:
        scope = sentry_sdk.get_current_scope()
        plan = self.get_context().request_plan
        if plan is None:
            return
        scope.set_tag('plan_id', plan.identifier)
        # scope.set_tag('plan_uuid', str(plan.uuid))

    @contextmanager
    def instance_context(self, operation: OperationDefinitionNode):
        ctx = self.get_context()
        assert ctx.graphql_query_language is not None
        with ExitStack() as stack:
            stack.enter_context(self.activate_language(ctx.graphql_query_language))
            yield


    def on_execute(self) -> Generator[None]:
        doc = self.execution_context.graphql_document
        if doc:
            op = get_first_operation(doc)
        else:
            op = None

        if not op or self.execution_context.result:
            yield
            return

        with self.instance_context(op):
            yield

class WatchExecutionCacheExtension(ExecutionCacheExtension[WatchGraphQLContext]):
    context_class: type[WatchGraphQLContext] = WatchGraphQLContext

    def get_cache_key_parts(self) -> list[str] | None:
        exec_ctx = self.get_context()
        plan = exec_ctx.request_plan
        if plan is None:
            self.set_reason('no plan')
            return None

        parts = [str(plan.identifier), plan.cache_invalidated_at.isoformat()]
        return parts

    def on_execute(self) -> Generator[None]:
        if env_bool('DEBUG_MODEL_CREATION', default=False):
            with ModelCreationCounter():
                yield from super().on_execute()
        else:
            yield from super().on_execute()


class WatchAuthenticationExtension(AuthenticationExtension[WatchGraphQLContext]):
    context_class: type[WatchGraphQLContext] = WatchGraphQLContext
