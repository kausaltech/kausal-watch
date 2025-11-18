from __future__ import annotations

from dataclasses import dataclass
from itertools import chain
from typing import TYPE_CHECKING, Any, cast

import graphene
from django.db.models import Q
from django.utils.translation import get_language
from graphql.error import GraphQLError
from wagtail.models import Page

from grapple.types.interfaces import get_page_interface
from loguru import logger

from actions.models import Action, Plan
from actions.schema import ActionNode
from indicators.models import Indicator, IndicatorQuerySet
from indicators.schema import IndicatorNode
from pages.models import AplansPage, PlanRootPage

if TYPE_CHECKING:
    from wagtail.query import PageQuerySet

    from aplans.graphql_types import GQLInfo

    from actions.models.action import ActionQuerySet


class SearchHitObject(graphene.Union):
    class Meta:
        types = (
            ActionNode,
            IndicatorNode,
        )


@dataclass
class SearchHitObj:
    id: str
    title: str
    plan: Plan
    object: Action | Indicator | None = None
    relevance: float = 0.0
    highlight: str | None = None
    page: Page | None = None


class SearchHit(graphene.ObjectType[SearchHitObj]):
    id = graphene.ID(required=True)
    title = graphene.String(required=True)
    url = graphene.String(client_url=graphene.String(required=False))
    relevance = graphene.Float(required=True)
    highlight = graphene.String(required=False)
    plan = graphene.Field('actions.schema.PlanNode', required=True)
    object = graphene.Field(SearchHitObject, required=False)
    page = graphene.Field(get_page_interface, required=False)

    @staticmethod
    def resolve_url(root: SearchHitObj, info, client_url=None) -> None | str:
        plan = root.plan
        if not plan or not plan.is_visible_for_user(info.context.user):
            return None

        # Check if this is a search result from other plans, we want to use the site_url for these.
        only_other_plans = getattr(info.context, 'only_other_plans', False)
        if only_other_plans:
            client_url = None

        search_hit_object = root.object
        page = root.page
        if search_hit_object is not None:
            return search_hit_object.get_view_url(plan=plan, client_url=client_url, request=info.context)
        if page is not None:
            parts = page.get_url_parts(request=info.context)
            if parts is None:
                return None
            return '%s%s' % (plan.get_view_url(client_url=client_url, request=info.context), parts[2])
        return None


class SearchResults(graphene.ObjectType[Any]):
    hits = graphene.List(graphene.NonNull(SearchHit), required=True)

    @staticmethod
    def resolve_hits(root, _info: GQLInfo) -> list[SearchHitObj]:
        hits = root['hits']
        res = []
        for obj in hits:
            if isinstance(obj, Action):
                hit = SearchHitObj(
                    id='act-%d' % obj.pk,
                    title=str(obj),
                    plan=obj.plan,
                    object=obj,
                )
            elif isinstance(obj, Indicator):
                plan = obj.plans.first()
                if not plan:
                    logger.warning('Indicator %d has no plan' % obj.pk)
                    continue
                hit = SearchHitObj(
                    id='ind-%d' % obj.pk,
                    title=str(obj),
                    plan=cast('Plan', obj.plans.first()),
                    object=obj,
                )
            elif isinstance(obj, AplansPage):
                plan = obj.plan
                if not plan:
                    logger.warning('AplansPage %d has no plan' % obj.pk)
                    continue
                hit = SearchHitObj(
                    id='page-%d' % obj.pk,
                    title=obj.title,
                    plan=plan,
                    page=obj,
                )
            else:
                logger.warning('Unknown object type: %s' % type(obj))
                continue
            hit.relevance = obj.relevance  # pyright: ignore
            highlights = getattr(obj, '_highlights', None)
            if highlights:
                hit.highlight = highlights[0]
            res.append(hit)
        return res


class Query:
    search = graphene.Field(
        SearchResults,
        plan=graphene.ID(required=True),
        include_related_plans=graphene.Boolean(default_value=False),
        only_other_plans=graphene.Boolean(default_value=False),
        max_results=graphene.Int(default_value=20),
        page=graphene.Int(default_value=0),
        query=graphene.String(required=False, default_value=None),
        autocomplete=graphene.String(required=False, default_value=None),
        required=True,
    )

    @staticmethod
    def resolve_search(  # noqa: ANN205, C901
        root,
        info,
        plan: str,
        include_related_plans=False,
        only_other_plans=False,
        max_results=20,
        page=0,
        query: str | None = None,
        autocomplete: str | None = None,
    ):
        if (query is not None and autocomplete is not None) or (query is None and autocomplete is None):
            raise GraphQLError('You must supply either query or autocomplete')

        plan_obj: Plan | None = Plan.objects.filter(identifier=plan).first()
        if plan_obj is None:
            raise GraphQLError('Plan %s not found' % plan)
        if not plan_obj.is_visible_for_user(info.context.user):
            raise GraphQLError('Plan %s not found' % plan)
        related_plans = plan_obj.get_all_related_plans().all()
        if plan_obj.is_live():
            # For live plans, restrict the related plans to be live also, preventing unreleased
            # plans from showing up in the production site
            related_plans = related_plans.live()
        if only_other_plans:
            plans = (
                Plan.objects.get_queryset()
                .live()
                .exclude(Q(id=plan_obj.id) | Q(id__in=related_plans) | Q(features__password_protected=True))
            )
        else:
            q = Q(id=plan_obj.id)
            if include_related_plans:
                q |= Q(id__in=related_plans.values_list('id', flat=True))
            plans = Plan.objects.get_queryset().filter(q)
        plans = plans.exclude(exclude_from_search=True).visible_for_user(info.context.user)
        plan_ids = list(plans.values_list('id', flat=True))

        # backend = get_search_backend()
        # backend.watch_search(query, included_plans=plan_ids)

        root_page_paths = PlanRootPage.objects.filter(sites_rooted_here__plan__in=plan_ids).values_list('path', flat=True)
        page_filter = Q(pk__in=[])  # always false; Q() doesn't cut it; https://stackoverflow.com/a/39001190/14595546
        for path in root_page_paths:
            page_filter |= Q(path__startswith=path)

        querysets: list[ActionQuerySet | PageQuerySet | IndicatorQuerySet] = [
            (
                Action.objects.get_queryset()
                .visible_for_user(info.context.user)
                .filter(plan__in=plan_ids)
                .select_related('plan', 'plan__organization')
            ),
            Page.objects.get_queryset().filter(page_filter).live().specific(),
        ]
        # FIXME: This doesn't work with exclude yet
        if not only_other_plans:
            querysets.append(Indicator.objects.get_queryset().visible_for_user(info.context.user).filter(plans__in=plan_ids))

        lang = get_language()
        # For now just string the region from the language as we don't have separate backends for regions at the moment
        lang = lang.split('-')[0]
        backend = 'default-%s' % lang
        results = []
        for qs in querysets:
            if autocomplete:
                res = qs.autocomplete(autocomplete, backend=backend)
            else:
                res = qs.search(query, backend=backend)
            res = res.annotate_score('relevance')[0:max_results]
            results.append(res)

        all_results = list(chain(*results))
        all_results.sort(key=lambda x: x.relevance, reverse=True)

        # Store only_other_plans in the context for use in resolve_url
        info.context.only_other_plans = only_other_plans

        return dict(hits=all_results)
