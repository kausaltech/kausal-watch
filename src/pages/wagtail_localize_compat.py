"""
Make wagtail-localize cope with struct blocks whose stored value is null.

Several blocks used to be `StaticBlock`s, which store their value as null. They are `StructBlock`s now, and they read
null as an empty struct (see `static_block_to_struct_compat()` and `RelatedPlanListBlock`), so pages and revisions
saved back then were left as they are. Such a struct gets the default value of each of its child blocks, which is
None for text blocks without an explicit default.

When wagtail-localize extracts the translatable segments of a page, e.g., to sync its translations or to copy it with
its plan, it fails on such blocks for two reasons:
- It looks at the raw value of each block. It copes with a struct block without a raw value, but not with one whose
  raw value is null.
- It expects the value of a text block to be a string.
"""

from __future__ import annotations

from typing import Any

from wagtail import blocks

from wagtail_localize.segments.extract import StreamFieldSegmentExtractor

_original_handle_block = StreamFieldSegmentExtractor.handle_block
_original_handle_struct_block = StreamFieldSegmentExtractor.handle_struct_block

TEXT_BLOCK_TYPES = (blocks.CharBlock, blocks.TextBlock, blocks.BlockQuoteBlock)


def _handle_block(self: StreamFieldSegmentExtractor, block_type: Any, block_value: Any, raw_value: Any = None) -> Any:
    if block_value is None and isinstance(block_type, TEXT_BLOCK_TYPES):
        # There is no text to translate
        return []
    return _original_handle_block(self, block_type, block_value, raw_value=raw_value)


def _handle_struct_block(self: StreamFieldSegmentExtractor, struct_block: Any, raw_value: Any = None) -> Any:
    if isinstance(raw_value, dict) and 'value' in raw_value and raw_value['value'] is None:
        # Same as for a block without a raw value
        raw_value = None
    return _original_handle_struct_block(self, struct_block, raw_value=raw_value)


def patch_segment_extraction() -> None:
    StreamFieldSegmentExtractor.handle_block = _handle_block  # type: ignore[method-assign]
    StreamFieldSegmentExtractor.handle_struct_block = _handle_struct_block  # type: ignore[method-assign]
