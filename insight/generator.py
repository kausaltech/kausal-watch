from django.db.models import Q
from django.urls import reverse

from actions.models import Action
from indicators.models import Indicator, RelatedIndicator, ActionIndicator


class GraphGenerator:
    def __init__(self, request=None):
        self.nodes = {}
        self.edges = {}
        self.request = request

    def get_graph(self):
        return dict(nodes=list(self.nodes.values()), edges=list(self.edges.values()))


class ActionGraphGenerator(GraphGenerator):
    def __init__(self, request=None, plan=None, traverse_direction='both'):
        super().__init__(request)
        self.plan = plan
        assert traverse_direction in ('forward', 'backward', 'both')
        self.traverse_direction = traverse_direction
        self.actions = {}
        self.indicators = {}

    def fetch_data(self):
        action_qs = self.plan.actions.visible_for_user(None).unmerged()
        self.actions = {obj.id: obj for obj in action_qs}
        action_indicators = ActionIndicator.objects.filter(action__in=action_qs)
        for ai in action_indicators:
            act = self.actions[ai.action_id]
            if not hasattr(act, '_indicators'):
                act._indicators = []
            act._indicators.append(ai)
        indicator_levels = self.plan.indicator_levels.all().select_related(
            'indicator', 'indicator__latest_value', 'indicator__unit'
        )
        indicators = {}
        for level in indicator_levels:
            indicator = level.indicator
            indicator.level = level.level
            indicator._effect_relations = []
            indicator._causal_relations = []
            indicators[indicator.id] = indicator
        self.indicators = indicators
        indicator_list = indicators.values()
        query = Q(causal_indicator__in=indicator_list) & Q(effect_indicator__in=indicator_list)
        for edge in RelatedIndicator.objects.filter(query):
            causal = indicators[edge.causal_indicator_id]
            effect = indicators[edge.effect_indicator_id]

            causal._effect_relations.append(edge)
            effect._causal_relations.append(edge)

    def make_node_id(self, obj):
        if isinstance(obj, Action):
            type_char = 'a'
        else:
            type_char = 'i'
        return f'{type_char}{obj.id}'

    def make_edge_id(self, src, target):
        return f'{self.make_node_id(src)}-{self.make_node_id(target)}'

    def get_indicator_level(self, obj):
        if hasattr(obj, 'level'):
            return obj.level
        for lo in obj.levels.all():
            if lo.plan_id == self.plan.id:
                return lo.level
        else:
            return ''

    def make_node(self, obj):
        d = {}
        if isinstance(obj, Action):
            url = reverse('action-detail', kwargs={'plan_pk': obj.plan.pk, 'pk': obj.pk})
            obj_type = 'action'
        elif isinstance(obj, Indicator):
            url = reverse('indicator-detail', kwargs={'plan_pk': self.plan.pk, 'pk': obj.pk})
            obj_type = 'indicator'
            d['indicator_level'] = self.get_indicator_level(obj)
            d['time_resolution'] = obj.time_resolution

            if obj.latest_value is not None:
                lv = obj.latest_value
                date = lv.date.isoformat()
                d['latest_value'] = dict(value=lv.value, date=date, unit=obj.unit.name)
            else:
                d['latest_value'] = None

        d['url'] = self.request.build_absolute_uri(url) if self.request else url
        d['type'] = obj_type
        d['object_id'] = obj.id
        d['name'] = obj.name_i18n
        d['id'] = self.make_node_id(obj)
        d['identifier'] = obj.identifier if obj.identifier else None

        return d

    def make_edge(self, src, target, effect_type=None, confidence_level=None):
        d = {}
        d['id'] = self.make_edge_id(src, target)
        d['from'] = self.make_node_id(src)
        d['to'] = self.make_node_id(target)
        if effect_type:
            d['effect_type'] = effect_type
        if confidence_level:
            d['confidence_level'] = confidence_level
        return d

    def add_edge(self, src, target, effect_type=None, confidence_level=None):
        edge_id = self.make_edge_id(src, target)
        if edge_id in self.edges:
            return

        edge = self.make_edge(src, target, effect_type, confidence_level)
        self.edges[edge_id] = edge

    def filter_indicators(self, qs, attr_name):
        if self.plan:
            filter_name = '%s__levels__plan' % attr_name
            qs = qs.filter(**{filter_name: self.plan})
        return qs.select_related(attr_name).prefetch_related('%s__levels' % attr_name)

    def get_related_indicators(self, obj, relation_type):
        if relation_type == 'effect':
            if hasattr(obj, '_effect_relations'):
                return obj._effect_relations
            else:
                return self.filter_indicators(obj.related_effects.all(), 'effect_indicator')
        elif relation_type == 'causal':
            if hasattr(obj, '_causal_relations'):
                return obj._causal_relations
            else:
                return self.filter_indicators(obj.related_causes.all(), 'causal_indicator')

    def add_node(self, obj):
        node_id = self.make_node_id(obj)
        if node_id in self.nodes:
            return

        self.nodes[node_id] = self.make_node(obj)

        if isinstance(obj, Action):
            if obj.id in self.actions:
                obj = self.actions[obj.id]
            if self.traverse_direction in ('forward', 'both'):
                if hasattr(obj, '_indicators'):
                    related_indicators = obj._indicators
                else:
                    related_indicators = obj.related_indicators.all()
                for ri in related_indicators:
                    if ri.indicator_id in self.indicators:
                        target = self.indicators[ri.indicator_id]
                    else:
                        target = ri.indicator
                    self.add_edge(
                        obj, target, ri.effect_type, RelatedIndicator.HIGH_CONFIDENCE
                    )
                    self.add_node(target)
        elif isinstance(obj, Indicator):
            if obj.id in self.indicators:
                obj = self.indicators[obj.id]
            if self.traverse_direction in ('forward', 'both'):
                for related in self.get_related_indicators(obj, 'effect'):
                    target = self.indicators.get(related.effect_indicator_id, None)
                    if target is None:
                        target = related.effect_indicator
                    self.add_edge(obj, target, related.effect_type, related.confidence_level)
                    self.add_node(target)

            if self.traverse_direction in ('backward', 'both'):
                for related in self.get_related_indicators(obj, 'causal'):
                    source = self.indicators.get(related.causal_indicator_id, None)
                    if source is None:
                        source = related.causal_indicator
                    self.add_edge(source, obj, related.effect_type, related.confidence_level)
                    self.add_node(source)


class OrganizationGraphGenerator(GraphGenerator):
    def __init__(self, request=None, orgs=[], classifications=[]):
        super().__init__(request)
        self.orgs = {org.id: org for org in orgs}
        self.org_classes = {kls.id: kls for kls in classifications}
        for org in orgs:
            self.add_node(org)

    def make_node_id(self, obj):
        return f'{obj.id}'

    def make_edge_id(self, src, target):
        return f'{self.make_node_id(src)}-{self.make_node_id(target)}'

    def make_node(self, obj):
        d = {}
        url = reverse('organization-detail', kwargs={'pk': obj.pk})
        d['url'] = self.request.build_absolute_uri(url) if self.request else url
        d['abbreviation'] = obj.abbreviation
        d['type'] = 'organization'
        d['classification'] = self.org_classes.get(obj.classification_id).name
        d['object_id'] = obj.id
        d['name'] = obj.name
        d['id'] = self.make_node_id(obj)
        return d

    def make_edge(self, src, target):
        d = {}
        d['id'] = self.make_edge_id(src, target)
        d['from'] = self.make_node_id(src)
        d['to'] = self.make_node_id(target)
        return d

    def add_node(self, obj):
        node_id = self.make_node_id(obj)
        if node_id in self.nodes:
            return

        self.nodes[node_id] = self.make_node(obj)
        if obj.parent_id:
            parent_obj = self.orgs[obj.parent_id]
            self.add_node(parent_obj)
            self.add_edge(parent_obj, obj)

    def add_edge(self, src, target):
        edge_id = self.make_edge_id(src, target)
        if edge_id in self.edges:
            return

        edge = self.make_edge(src, target)
        self.edges[edge_id] = edge
