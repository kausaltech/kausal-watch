"""
Configure the kausal_common.datasets app.

There is some project-specific configration required for the reusable datasets apps
found in kausal_common.datasets to make it adapt to different use cases in Watch
and Paths. The configuration must be found in the module
dataset_config under the project directory.
"""
from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from django.db.models import Model

    from aplans.types import WatchAdminRequest

def schema_default_scope():
    # Only call in view contexts where the context has been initialized
    from aplans.context_vars import ctx_request
    request = typing.cast('WatchAdminRequest', ctx_request.get())
    return request.get_active_admin_plan()


DATA_SOURCE_DEFAULT_SCOPE_CONTENT_TYPE = ('actions', 'plan')
SCHEMA_HAS_SINGLE_DATASET: bool = False
SCHEMA_DEFAULT_SCOPE_FUNCTION: Callable[[], Model] | None = schema_default_scope
# Permission policies for datasets
SHOW_DATASETS_IN_MENU: bool = False
SHOW_SCHEMAS_IN_MENU: bool = False
SCHEMA_PERMISSION_POLICY = 'datasets.permission_policy.DatasetSchemaPermissionPolicy'
DATASET_PERMISSION_POLICY = 'datasets.permission_policy.ScopeInheritedDatasetPermissionPolicy'
DATA_POINT_PERMISSION_POLICY = 'datasets.permission_policy.DataPointPermissionPolicy'
DATA_SOURCE_PERMISSION_POLICY = 'datasets.permission_policy.DataSourcePermissionPolicy'
