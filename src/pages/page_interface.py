from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

import graphene

from grapple.types.interfaces import PageInterface as BasePageInterface, get_page_interface

if TYPE_CHECKING:
    from wagtail.models import Page

    from aplans.cache import PlanSpecificCache
    from aplans.graphql_types import GQLInfo

    from pages.models import AplansPage
    from users.models import User


def get_site_by_plan(user: User):
    plan = user.get_active_admin_plan()
    if not plan:
        return None, None

    root_page = plan.root_page
    if root_page:
        root_site = root_page.get_site()
    else:
        root_site = None
    return root_site, root_page


@dataclass
class VisibleSpecificPage:
    page: AplansPage
    cache: PlanSpecificCache

    @classmethod
    def from_page(cls, page: Page, info: GQLInfo) -> Self | None:
        cache = info.context.cache.for_page_path(page.path)
        if cache is None:
            return None
        for visible_page in cache.visible_pages:
            if visible_page.path == page.path:
                return cls(page=visible_page, cache=cache)
        return None


class PageInterface(BasePageInterface):
    children = graphene.List(graphene.NonNull(get_page_interface), required=True)
    siblings = graphene.List(graphene.NonNull(get_page_interface), required=True)
    next_siblings = graphene.List(graphene.NonNull(get_page_interface), required=True)
    previous_siblings = graphene.List(graphene.NonNull(get_page_interface), required=True)
    ancestors = graphene.List(graphene.NonNull(get_page_interface), required=True)

    content_type = None

    @staticmethod
    def resolve_url_path(root: Page, _info: GQLInfo) -> str:
        # Strip the trailing '/'
        return root.url_path.rstrip('/')

    @staticmethod
    def resolve_parent(root: Page, info: GQLInfo) -> Page | None:
        specific = VisibleSpecificPage.from_page(root, info)
        if specific is None:
            return None
        return specific.page.get_visible_parent(specific.cache)

    @staticmethod
    def resolve_children(root: Page, info: GQLInfo) -> list[AplansPage]:
        specific = VisibleSpecificPage.from_page(root, info)
        if specific is None:
            return []
        return specific.page.get_visible_children(specific.cache)

    @staticmethod
    def resolve_siblings(root: Page, info: GQLInfo) -> list[AplansPage]:
        return []

    resolve_next_siblings = resolve_siblings  # pyright: ignore[reportAssignmentType]
    resolve_previous_siblings = resolve_siblings  # pyright: ignore[reportAssignmentType]

    @staticmethod
    def resolve_ancestors(root: Page, info: GQLInfo) -> list[AplansPage]:
        specific = VisibleSpecificPage.from_page(root, info)
        if specific is None:
            return []
        return specific.page.get_visible_ancestors(specific.cache)
