from wagtail.admin.telepath import JSContext

import pytest

from aplans.cache import PlanSpecificCache
from aplans.context_vars import ctx_request

from actions.tests.factories import PlanFactory
from indicators.blocks.layout import (
    FeatureGatedStreamBlockAdapter,
    IndicatorAsideContentStream,
    IndicatorMainContentStream,
)

pytestmark = pytest.mark.django_db


def _grouped_block_names(js_args) -> set[str]:
    names: set[str] = set()
    for _group, child_blocks in js_args[1]:
        names.update(b.name for b in child_blocks)
    return names


def _block_counts(js_args) -> dict:
    return js_args[3].get('blockCounts') or {}


def _activate_request(rf, plan):
    request = rf.get('/')
    request.admin_cache = PlanSpecificCache(plan=plan)
    return request


class TestFeatureGatedStreamBlockAdapter:
    adapter = FeatureGatedStreamBlockAdapter()

    def test_all_block_defs_present_when_feature_disabled(self, rf):
        plan = PlanFactory.create(features__enable_indicator_factors=False)
        block = IndicatorMainContentStream()
        with ctx_request.activate(_activate_request(rf, plan)):
            args = self.adapter.js_args(block)
        assert 'factor_value_summary' in _grouped_block_names(args)

    def test_block_counts_max_zero_when_feature_disabled(self, rf):
        plan = PlanFactory.create(features__enable_indicator_factors=False)
        block = IndicatorMainContentStream()
        with ctx_request.activate(_activate_request(rf, plan)):
            args = self.adapter.js_args(block)
        assert _block_counts(args).get('factor_value_summary') == {'max_num': 0}

    def test_no_restriction_when_feature_enabled(self, rf):
        plan = PlanFactory.create(features__enable_indicator_factors=True)
        block = IndicatorMainContentStream()
        with ctx_request.activate(_activate_request(rf, plan)):
            args = self.adapter.js_args(block)
        assert 'factor_value_summary' not in _block_counts(args)

    def test_no_restriction_without_admin_context(self):
        block = IndicatorMainContentStream()
        args = self.adapter.js_args(block)
        assert 'factor_value_summary' not in _block_counts(args)

    def test_aside_stream_ignores_missing_gated_block(self, rf):
        plan = PlanFactory.create(features__enable_indicator_factors=False)
        block = IndicatorAsideContentStream()
        with ctx_request.activate(_activate_request(rf, plan)):
            args = self.adapter.js_args(block)
        assert 'factor_value_summary' not in _block_counts(args)

    def test_child_blocks_contains_all_blocks(self, rf):
        plan = PlanFactory.create(features__enable_indicator_factors=False)
        block = IndicatorMainContentStream()
        with ctx_request.activate(_activate_request(rf, plan)):
            names = {b.name for b in block.child_blocks.values()}
        assert 'factor_value_summary' in names

    def test_telepath_pack_does_not_crash_when_feature_disabled(self, rf):
        plan = PlanFactory.create(features__enable_indicator_factors=False)
        block = IndicatorMainContentStream()
        with ctx_request.activate(_activate_request(rf, plan)):
            JSContext().pack(block)
