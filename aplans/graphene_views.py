import hashlib
import json
import logging

from django.conf import settings
from django.utils import translation
from django.core.cache import cache

import sentry_sdk
from actions.models import Plan
from django.core.exceptions import ValidationError
from graphene_django.views import GraphQLView
from graphql import ExecutionResult
from graphql.error import GraphQLError
from graphql.language.ast import VariableNode
from rich.console import Console
from rich.syntax import Syntax

from .graphql_helpers import GraphQLAuthFailedError, GraphQLAuthRequiredError
from .graphql_types import AuthenticatedUserNode
from .code_rev import REVISION
from users.models import User

SUPPORTED_LANGUAGES = {x[0].lower() for x in settings.LANGUAGES}
logger = logging.getLogger(__name__)


class APITokenMiddleware:
    # def authenticate_user(self, info):
    #     raise GraphQLError('Token not found', [info])

    def process_auth_directive(self, info, directive):
        user = None
        token = None
        variable_vals = info.variable_values
        for arg in directive.arguments:
            if arg.name.value == 'uuid':
                if isinstance(arg.value, VariableNode):
                    val = variable_vals.get(arg.value.name.value)
                else:
                    val = arg.value.value
                try:
                    user = User.objects.get(uuid=val)
                except User.DoesNotExist:
                    raise GraphQLAuthFailedError("User not found", [arg])
                except ValidationError:
                    raise GraphQLAuthFailedError("Invalid UUID", [arg])

            elif arg.name.value == 'token':
                if isinstance(arg.value, VariableNode):
                    val = variable_vals.get(arg.value.name.value)
                else:
                    val = arg.value.value
                token = val

        if not token:
            raise GraphQLAuthFailedError("Token required", [directive])
        if not user:
            raise GraphQLAuthFailedError("User required", [directive])

        try:
            if user.auth_token.key != token:
                raise GraphQLAuthFailedError("Invalid token", [directive])
        except User.auth_token.RelatedObjectDoesNotExist:
            raise GraphQLAuthFailedError("Invalid token", [directive])

        info.context.user = user

    def resolve(self, next, root, info, **kwargs):
        context = info.context

        if root is None:
            operation = info.operation
            for directive in operation.directives:
                if directive.name.value == 'auth':
                    self.process_auth_directive(info, directive)

        rt = info.return_type
        gt = getattr(rt, 'graphene_type', None)
        if gt and issubclass(gt, AuthenticatedUserNode):
            if not getattr(context, 'user', None):
                raise GraphQLAuthRequiredError("Authentication required", [info])
        return next(root, info, **kwargs)


class LocaleMiddleware:
    def process_locale_directive(self, info, directive):
        variable_vals = info.variable_values
        for arg in directive.arguments:
            if arg.name.value == 'lang':
                if isinstance(arg.value, Variable):
                    lang = variable_vals.get(arg.value.name.value)
                else:
                    lang = arg.value.value
                if lang.lower() not in SUPPORTED_LANGUAGES:
                    raise GraphQLError("unsupported language: %s" % lang, [info])
                info.context._graphql_query_language = lang
                return lang

    def resolve(self, next, root, info, **kwargs):
        if root is None:
            info.context._graphql_query_language = None
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


class SentryGraphQLView(GraphQLView):
    def __init__(self, *args, **kwargs):
        if 'middleware' not in kwargs:
            kwargs['middleware'] = (APITokenMiddleware, LocaleMiddleware)
        super().__init__(*args, **kwargs)

    def get_cache_key(self, request, data, query, variables):
        plan_identifier = request.headers.get('x-cache-plan-identifier')
        plan_domain = request.headers.get('x-cache-plan-domain')
        if not plan_identifier and not plan_domain:
            return None

        qs = Plan.objects
        if plan_identifier:
            qs = qs.filter(identifier=plan_identifier)
        if plan_domain:
            qs = qs.for_hostname(plan_domain)
        plan = qs.first()
        if plan is None:
            return None

        m = hashlib.sha1()
        m.update(REVISION.encode('utf8'))
        m.update(plan.cache_invalidated_at.isoformat().encode('utf8'))
        m.update(json.dumps(variables).encode('utf8'))
        m.update(query.encode('utf8'))
        key = m.hexdigest()
        return key

    def get_from_cache(self, key):
        return cache.get(key)

    def store_to_cache(self, key, result):
        return cache.set(key, result, timeout=600)

    def caching_execute_graphql_request(self, span, request, data, query, variables, operation_name, *args, **kwargs) -> ExecutionResult:
        key = self.get_cache_key(request, data, query, variables)
        span.set_tag('cache_key', key)
        if key:
            result = self.get_from_cache(key)
            if result is not None:
                span.set_tag('cache', 'hit')
                return result

        span.set_tag('cache', 'miss')
        result = super().execute_graphql_request(request, data, query, variables, operation_name, *args, **kwargs)
        if key and not result.errors:
            self.store_to_cache(key, result)

        return result

    def execute_graphql_request(self, request, data, query, variables, operation_name, *args, **kwargs):
        """Execute GraphQL request, cache results and send exceptions to Sentry"""
        request._referer = self.request.META.get('HTTP_REFERER')
        transaction = sentry_sdk.Hub.current.scope.transaction
        logger.info('GraphQL request %s from %s' % (operation_name, request._referer))
        if settings.DEBUG and logger.isEnabledFor(logging.DEBUG) and query:
            console = Console()
            syntax = Syntax(query, "graphql")
            console.print(syntax)
            if variables:
                console.print('Variables:', variables)

        with sentry_sdk.push_scope() as scope:
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
                span = sentry_sdk.tracing.Span()

            with span:
                result = self.caching_execute_graphql_request(
                    span, request, data, query, variables, operation_name, *args, **kwargs
                )

            # If 'invalid' is set, it's a bad request
            if result and result.errors:
                # FIXME: Check for result.invalid
                for error in result.errors:
                    """
                    print(error)
                    err = error.original_error
                    tb = Traceback.from_exception(type(err), err, traceback=err.__traceback__)
                    console.print(tb)
                    """
                    if hasattr(error, 'original_error'):
                        error = error.original_error
                    sentry_sdk.capture_exception(error)

        return result
