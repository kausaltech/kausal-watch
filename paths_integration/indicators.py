from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext as _

from paths_integration._generated_.graphql_client.client import PathsClient

if TYPE_CHECKING:
    from actions.models import Plan
    from indicators.models import Indicator
    from paths_integration._generated_.graphql_client.node_values import NodeValuesNodeMetricDim


async def get_indicator_values(plan: Plan, indicator: Indicator) -> dict[str, Any]:
    assert plan.kausal_paths_instance_uuid
    client_url = os.getenv('PATHS_BACKEND_URL', 'https://api.paths.kausal.dev') + '/v1/graphql/'
    client = PathsClient(url=client_url)
    response = await client.node_values(
        lang=plan.primary_language,
        instance_id=plan.kausal_paths_instance_uuid,
        node_id=indicator.kausal_paths_node_uuid,
    )
    node = response.node
    instance = response.instance
    if node is None:
        raise ValueError(
            _('Node %(node)s not found in Paths instance %(instance)s') % {
                'node': indicator.kausal_paths_node_uuid,
                'instance': plan.kausal_paths_instance_uuid,
            })
    metric_dim = node.metric_dim
    if metric_dim is None:
        raise ValueError(
            _('No values received for node %(node)s in Paths instance %(instance)') % {
                'node': indicator.kausal_paths_node_uuid,
                'instance':  plan.kausal_paths_instance_uuid,
            }
        )

    return {
        'instance': instance,
        'node': node,
        'dimensional_metric': metric_dim,
        'source_url': client_url,
        }
