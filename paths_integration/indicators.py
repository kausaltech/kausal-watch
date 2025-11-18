from __future__ import annotations

import os
from typing import TYPE_CHECKING

from paths_integration._generated_.graphql_client.client import PathsClient

if TYPE_CHECKING:
    from actions.models import Plan
    from indicators.models import Indicator
    from paths_integration._generated_.graphql_client.node_values import NodeValuesNodeMetricDim


async def get_indicator_values(plan: Plan, indicator: Indicator) -> NodeValuesNodeMetricDim:
    assert plan.kausal_paths_instance_uuid
    client = PathsClient(url=os.getenv('PATHS_BACKEND_URL', 'https://api.paths.kausal.dev') + '/v1/graphql/')
    response = await client.node_values(
        lang='en',
        instance_id=plan.kausal_paths_instance_uuid,
        node_id='net_emissions',  # indicator.kausal_paths_node_uuid,
    )
    node = response.node
    assert node is not None
    metric_dim = node.metric_dim
    assert metric_dim is not None
    return metric_dim


if __name__ == '__main__':
    import asyncio

    from kausal_common.development.django import init_django
    from rich import print
    init_django()
    from actions.models import Plan
    plan = Plan.objects.exclude(kausal_paths_instance_uuid__isnull=True).exclude(kausal_paths_instance_uuid='').filter()[0]
    print(plan)
    indicator = plan.indicators.all()[0]
    metric_dim = asyncio.run(get_indicator_values(plan, indicator))
    print(metric_dim)
