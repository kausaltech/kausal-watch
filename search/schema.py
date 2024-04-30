import logging
from itertools import chain
from typing import Optional

from django.utils.translation import get_language
from django.db.models import Q
import graphene
from graphql.error import GraphQLError
from wagtail.models import Page

from actions.models import Action, Plan
from indicators.models import Indicator
from pages.models import PlanRootPage, AplansPage

from actions.schema import ActionNode
from indicators.schema import IndicatorNode
from .backends import get_search_backend


logger = logging.getLogger(__name__)


class SearchHitObject(graphene.Union):
    class Meta:
        types = (
            ActionNode, IndicatorNode,
        )


class SearchHit(graphene.ObjectType):
    id = graphene.ID()
    title = graphene.String()
    url = graphene.String(client_url=graphene.String(required=False))
    relevance = graphene.Float()
    highlight = graphene.String()
    plan = graphene.Field('actions.schema.PlanNode')
    object = graphene.Field(SearchHitObject, required=False)
    page = graphene.Field('grapple.types.pages.PageInterface', required=False)

    def resolve_url(root, info, client_url=None):
        object = root.get('object')
        page = root.get('page')
        plan = root['plan']
        if object is not None:
            return object.get_view_url(plan=plan, client_url=client_url)
        elif page is not None:
            parts = page.get_url_parts(request=info.context)
            return '%s%s' % (plan.get_view_url(client_url=client_url), parts[2])
        return None


class SearchResults(graphene.ObjectType):
    hits = graphene.List(SearchHit)

    def resolve_hits(root, info):
        hits = root['hits']
        res = []
        for obj in hits:
            if isinstance(obj, Action):
                hit = dict(
                    id='act-%d' % obj.id,
                    title=str(obj),
                    plan=obj.plan,
                    object=obj
                )
            elif isinstance(obj, Indicator):
                hit = dict(
                    id='ind-%d' % obj.id,
                    title=str(obj),
                    plan=obj.plans.first(),
                    object=obj,
                )
            elif isinstance(obj, AplansPage):
                hit = dict(
                    id='page-%d' % obj.id,
                    title=obj.title,
                    plan=obj.plan,
                    page=obj,
                )
            else:
                logger.warning('Unknown object type: %s' % type(obj))
                continue
            hit['relevance'] = obj.relevance
            highlights = getattr(obj, '_highlights', None)
            if highlights:
                hit['highlight'] = highlights[0]
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
    )

    def resolve_search(
        root, info, plan, include_related_plans=False, only_other_plans=False,
        max_results=20, page=0, query=None, autocomplete=None,
    ):
        if ((query is not None and autocomplete is not None) or
                (query is None and autocomplete is None)):
            raise GraphQLError("You must supply either query or autocomplete")

        plan_obj: Optional[Plan] = Plan.objects.filter(identifier=plan).first()
        if plan_obj is None:
            raise GraphQLError("Plan %s not found" % plan)
        related_plans = plan_obj.get_all_related_plans().all()
        if plan_obj.is_live():
            # For live plans, restrict the related plans to be live also, preventing unreleased plans from showing up in the production site
            related_plans = related_plans.live()
        if only_other_plans:
            plans = Plan.objects.live().exclude(Q(id=plan_obj.id) | Q(id__in=related_plans) | Q(features__password_protected=True))
        else:
            qs = Q(id=plan_obj.id)
            if include_related_plans:
                qs |= Q(id__in=related_plans.values_list('id', flat=True))
            plans = Plan.objects.filter(qs)

        plan_ids = list(plans.values_list('id', flat=True))

        #backend = get_search_backend()
        #backend.watch_search(query, included_plans=plan_ids)

        root_page_paths = (
            PlanRootPage.objects
                .filter(sites_rooted_here__plan__in=plan_ids)
                .values_list('path', flat=True)
        )
        page_filter = Q(pk__in=[])  # always false; Q() doesn't cut it; https://stackoverflow.com/a/39001190/14595546
        for path in root_page_paths:
            page_filter |= Q(path__startswith=path)

        querysets = [
            Action.objects.visible_for_user(None).filter(plan__in=plan_ids).select_related('plan', 'plan__organization'),
            Page.objects.filter(page_filter).live().specific(),
        ]
        # FIXME: This doesn't work with exclude yet
        if not only_other_plans:
            querysets.append(Indicator.objects.visible_for_user(None).filter(plans__in=plan_ids))


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
        return dict(hits=all_results)
