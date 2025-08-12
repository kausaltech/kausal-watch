from __future__ import annotations

from typing import TYPE_CHECKING, Any

import graphene
from django.utils.module_loading import import_string
from graphql.error import GraphQLError
from graphql.utilities.ast_to_dict import ast_to_dict

from kausal_common.users import user_or_bust

from admin_site.permissions import PlanRelatedPermissionPolicy
from admin_site.wagtail import AplansModelAdmin, PlanRelatedModelAdminPermissionHelper

from .graphql_types import AdminButton

if TYPE_CHECKING:
    from django.db.models import Model
    from graphql import GraphQLResolveInfo
    from wagtail.admin.widgets.button import Button

    from kausal_common.graphene import GQLInfo

    from admin_site.viewsets import WatchViewSet


def collect_fields(node, fragments):
    """
    Recursively collects fields from the AST.

    Args:
        node (dict): A node in the AST
        fragments (dict): Fragment definitions

    Returns:
        A dict mapping each field found, along with their sub fields.
        {'name': {},
         'sentimentsPerLanguage': {'id': {},
                                   'name': {},
                                   'totalSentiments': {}},
         'slug': {}}.

    """

    field = {}

    if node.get('selection_set'):
        for leaf in node['selection_set']['selections']:
            if leaf['kind'].lower() == 'field':
                field.update({
                    leaf['name']['value']: collect_fields(leaf, fragments),
                })
            elif leaf['kind'].replace('_', '').lower() == 'fragmentspread':
                field.update(collect_fields(fragments[leaf['name']['value']],
                                            fragments))

    return field


def get_fields(info: GraphQLResolveInfo):
    """
    Call collect_fields with info.

    Args:
        info (ResolveInfo): resolve info

    Returns:
        dict: Returned from collect_fields

    """

    fragments = {}
    node = ast_to_dict(info.field_nodes[0])

    for name, value in info.fragments.items():
        fragments[name] = ast_to_dict(value)

    return collect_fields(node, fragments)


class GraphQLAuthFailedError(GraphQLError):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.extensions:
            self.extensions = {
                'code': 'AUTH_FAILED',
            }


class GraphQLAuthRequiredError(GraphQLError):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.extensions:
            self.extensions = {
                'code': 'AUTH_REQUIRED',
            }

class ModelAdminAdminButtonsMixin:
    admin_buttons = graphene.List(graphene.NonNull(AdminButton), required=True)

    @staticmethod
    def resolve_admin_buttons(root: Model, info: GQLInfo) -> list[Button]:
        ModelAdmin: type[AplansModelAdmin[Any]] = import_string(root.MODEL_ADMIN_CLASS)  # type: ignore

        if not info.context.user.is_staff:
            return []
        adm = ModelAdmin()
        index_view = adm.index_view_class(adm)
        helper_class = adm.get_button_helper_class()
        helper = helper_class(index_view, info.context)
        if isinstance(helper.permission_helper, PlanRelatedModelAdminPermissionHelper):
            helper.permission_helper.disable_admin_plan_check()
        buttons = helper.get_buttons_for_obj(root)
        return buttons

class AdminButtonsMixin:
    admin_buttons = graphene.List(graphene.NonNull(AdminButton), required=True)

    @staticmethod
    def resolve_admin_buttons(root: Model, info: GQLInfo) -> list[AdminButton]:
        if not info.context.user.is_staff:
            return []

        view_set_class: type[WatchViewSet[Any]] = import_string(root.VIEWSET_CLASS)  # type: ignore
        view_set = view_set_class()

        if isinstance(view_set.permission_policy, PlanRelatedPermissionPolicy):
            view_set.permission_policy.disable_admin_plan_check()

        if not hasattr(view_set, 'get_index_view_buttons'):
            raise ValueError(f'get_index_view_buttons method not found for view set {view_set.__class__.__name__}')
        user = user_or_bust(info.context.user)
        plan = user.get_active_admin_plan()
        buttons = view_set.get_index_view_buttons(user, root, plan)  # type: ignore[attr-defined]

        # TODO: Temporary workaround to support both the new and old attribute
        # name for icon, making the code work for modeladmin code as well. The
        # GraphQL queries should be updated to use the new attribute name once
        # actions have migrated from modeladmin.
        for button in buttons:
            button.icon = button.icon_name

        return buttons
