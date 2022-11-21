from typing import Tuple
import typing

if typing.TYPE_CHECKING:
    from wagtail.core.blocks import Block


# Some ModelAdmins can be disabled if they are replaced in an extension.
disabled_modeladmins = set()


def disable_modeladmin(name):
    disabled_modeladmins.add(name)


def should_register_modeladmin(cls):
    fq_name = '%s.%s' % (cls.__module__, cls.__name__)
    if fq_name in disabled_modeladmins:
        return False
    else:
        return True


def modeladmin_register(cls):
    from wagtail.contrib.modeladmin.options import modeladmin_register as wagtail_modeladmin_register

    if not should_register_modeladmin(cls):
        return cls
    return wagtail_modeladmin_register(cls)


BlockDef = Tuple[str, 'Block']

body_block_registry: dict[str | None, list[BlockDef]] = dict()

blocks_callback_funcs = set()


def register_blocks_callback(func):
    global blocks_callback_funcs
    blocks_callback_funcs.add(func)


def register_body_block(key: str, block: 'Block', for_page: str | None = None):
    global body_block_registry

    if for_page not in body_block_registry:
        body_block_registry[for_page] = []

    block_list = body_block_registry[for_page]

    if key in [x[0] for x in block_list]:
        raise Exception("Block %s already defined" % key)

    block_list.append((key, block))


def get_body_blocks(for_page: str | None = None) -> list[BlockDef]:
    global blocks_callback_funcs
    if blocks_callback_funcs:
        for func in blocks_callback_funcs:
            func()
        blocks_callback_funcs = set()

    block_defs = body_block_registry.get(for_page, [])

    # Include blocks meant for all pages
    if for_page is not None:
        block_defs += body_block_registry.get(None, [])

    return block_defs
