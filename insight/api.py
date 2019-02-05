from rest_framework.response import Response
from .generator import GraphGenerator
from actions.models import Action, Plan
from aplans.utils import register_view_helper
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

all_views = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


class InsightViewSet(viewsets.ViewSet):
    def list(self, request):
        params = request.query_params
        plan_id = params.get('plan', '').strip()
        if not plan_id:
            raise ValidationError("You must supply a 'plan' filter")
        try:
            plan = Plan.objects.get(identifier=plan_id)
        except Plan.DoesNotExist:
            raise ValidationError("Plan %s does not exist" % plan_id)

        actions = Action.objects.filter(plan=plan, indicators__isnull=False)
        gg = GraphGenerator(request=request, plan=plan)
        for act in actions:
            gg.add_node(act)
        graph = gg.get_graph()
        return Response(graph)


register_view(klass=InsightViewSet, name='insight', basename='insight')
