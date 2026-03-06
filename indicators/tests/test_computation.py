from decimal import Decimal

import pytest

from indicators.computation import _apply_op


@pytest.mark.parametrize(('op', 'a', 'b', 'expected'), [
    ('multiply', Decimal(3), Decimal(5), Decimal(15)),
    ('multiply', Decimal(0), Decimal(5), Decimal(0)),
    ('multiply', Decimal(-2), Decimal(3), Decimal(-6)),
    ('divide', Decimal(10), Decimal(2), Decimal(5)),
    ('divide', Decimal(7), Decimal(3), Decimal(7) / Decimal(3)),
    ('divide', Decimal(10), Decimal(0), None),
    ('add', Decimal(3), Decimal(5), Decimal(8)),
    ('add', Decimal(-3), Decimal(5), Decimal(2)),
    ('subtract', Decimal(10), Decimal(3), Decimal(7)),
    ('subtract', Decimal(3), Decimal(10), Decimal(-7)),
])
def test_apply_op(op, a, b, expected):
    assert _apply_op(op, a, b) == expected


@pytest.mark.parametrize('op', ['multiply', 'divide', 'add', 'subtract'])
def test_apply_op_none_operand_a(op):
    assert _apply_op(op, None, Decimal(5)) is None


@pytest.mark.parametrize('op', ['multiply', 'divide', 'add', 'subtract'])
def test_apply_op_none_operand_b(op):
    assert _apply_op(op, Decimal(5), None) is None


@pytest.mark.parametrize('op', ['multiply', 'divide', 'add', 'subtract'])
def test_apply_op_both_none(op):
    assert _apply_op(op, None, None) is None


def test_apply_op_unknown_operation():
    with pytest.raises(ValueError, match='Unknown operation'):
        _apply_op('modulo', Decimal(5), Decimal(3))
