from itertools import chain

from django.utils.translation import get_language
import graphene
from graphql.error import GraphQLError
from wagtail.core.models import Page

from actions.models import Action, Plan
from indicators.models import Indicator


class SearchHit(graphene.ObjectType):
    title = graphene.String()
    url = graphene.String()
    relevance = graphene.Float()

    action = graphene.Field('actions.schema.ActionNode', required=False)
    indicator = graphene.Field('indicators.schema.IndicatorNode', required=False)
    page = graphene.Field('grapple.types.pages.PageInterface', required=False)


class SearchResults(graphene.ObjectType):
    hits = graphene.List(SearchHit)

    def resolve_hits(root, info):
        hits = root['hits']
        res = []
        for obj in hits:
            if isinstance(obj, Action):
                hit = dict(title=str(obj), url=obj.get_view_url(), action=obj)
            elif isinstance(obj, Indicator):
                hit = dict(title=str(obj), url=obj.get_view_url(), indicator=obj)
            elif isinstance(obj, Page):
                hit = dict(title=obj.page, url=obj.get_full_url(), page=obj)
            hit['relevance'] = obj.relevance
            res.append(hit)
        return res


class Query:
    search = graphene.Field(
        SearchResults,
        plan=graphene.ID(required=False),
        query=graphene.String(required=False),
        autocomplete=graphene.String(required=False),
        max_results=graphene.Int(default_value=10),
        page=graphene.Int(default_value=0)
    )

    def resolve_search(root, info, plan=None, query=None, autocomplete=None, max_results=10, page=0):
        if ((query is not None and autocomplete is not None) or
                (query is None and autocomplete is None)):
            raise GraphQLError("You must supply either query or autocomplete", [info])

        plans = Plan.objects.all()
        if plan is not None:
            plan_obj = Plan.objects.filter(identifier=plan).first()
            if plan_obj is None:
                raise GraphQLError("Plan %s not found" % plan, [info])
            plans = plans.filter(id=plan_obj.id)
            # FIXME: add related plans
        plans = list(plans.values_list('id', flat=True))

        querysets = [
            Action.objects.filter(plan__in=plans),
            Indicator.objects.filter(plans__in=plans),
            # FIXME: Add Pages
        ]
        lang = get_language()
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
