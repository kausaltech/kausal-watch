"""
Generated block classes are added to this module.

They can be imported into migrations from here.
"""

from __future__ import annotations

# Blocks that used to be generated and are now written by hand. Old migrations still import them from here.
FORMERLY_GENERATED_BLOCKS = {
    'ActionTasksBlock': 'actions.blocks.action_content_blocks',
}


def __getattr__(name: str) -> object:
    module_name = FORMERLY_GENERATED_BLOCKS.get(name)
    if module_name is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

    from importlib import import_module

    return getattr(import_module(module_name), name)
