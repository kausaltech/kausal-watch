from rest_framework.response import Response
from .generator import GraphGenerator
from actions.models import Action
from aplans.utils import register_view_helper
from rest_framework import viewsets

all_views = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


class InsightViewSet(viewsets.ViewSet):
    def list(self, request):
        gg = GraphGenerator(request=request)

        # params = request.query_params
        actions = Action.objects.filter(indicators__isnull=False)
        for act in actions:
            gg.add_node(act)
        graph = gg.get_graph()
        return Response(graph)


register_view(klass=InsightViewSet, name='insight', basename='insight')
