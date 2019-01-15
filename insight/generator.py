from django.urls import reverse
from actions.models import Action
from indicators.models import Indicator, RelatedIndicator


def make_node_id(obj):
    if isinstance(obj, Action):
        type_char = 'a'
    else:
        type_char = 'i'
    return f'{type_char}{obj.id}'


def make_edge_id(src, target):
    return f'{make_node_id(src)}-{make_node_id(target)}'


class GraphGenerator:
    def __init__(self, url_base=None):
        self.nodes = {}
        self.edges = {}
        self.url_base = url_base

    def make_node(self, obj):
        d = {}
        if isinstance(obj, Action):
            url = reverse('action-detail', kwargs={'pk': obj.pk})
            obj_type = 'action'
        elif isinstance(obj, Indicator):
            url = reverse('indicator-detail', kwargs={'pk': obj.pk})
            obj_type = 'indicator'
            d['indicator_level'] = obj.level

        d['url'] = (self.url_base or '') + url
        d['type'] = obj_type
        d['object_id'] = obj.id
        d['name'] = obj.name
        d['id'] = make_node_id(obj)
        return d

    def make_edge(self, src, target, effect_type=None, confidence_level=None):
        d = {}
        d['id'] = make_edge_id(src, target)
        d['from'] = make_node_id(src)
        d['to'] = make_node_id(target)
        if effect_type:
            d['effect_type'] = effect_type
        if confidence_level:
            d['confidence_level'] = confidence_level
        return d

    def add_edge(self, src, target, effect_type=None, confidence_level=None):
        edge_id = make_edge_id(src, target)
        if edge_id in self.edges:
            return

        edge = self.make_edge(src, target, effect_type, confidence_level)
        self.edges[edge_id] = edge

    def add_node(self, obj):
        node_id = make_node_id(obj)
        if node_id in self.nodes:
            return

        self.nodes[node_id] = self.make_node(obj)

        if isinstance(obj, Action):
            for indicator in obj.indicators.all():
                self.add_edge(
                    obj, indicator, RelatedIndicator.INCREASES,
                    RelatedIndicator.HIGH_CONFIDENCE
                )
                self.add_node(indicator)
        elif isinstance(obj, Indicator):
            for related in obj.related_effects.all():
                target = related.effect_indicator
                self.add_edge(obj, target, related.effect_type, related.confidence_level)
                self.add_node(target)

            for related in obj.related_causes.all():
                source = related.causal_indicator
                self.add_edge(source, obj, related.effect_type, related.confidence_level)
                self.add_node(source)

    def get_graph(self):
        return dict(nodes=list(self.nodes.values()), edges=list(self.edges.values()))
