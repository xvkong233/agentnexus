"""计费引擎单测：Decimal 精度、加价率、差值幂等。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal  # noqa: E402

from app.models import PricingRule  # noqa: E402
from app.services.billing import compute_costs, effective_prices, q6  # noqa: E402


def _rule(**kw) -> PricingRule:
    defaults = dict(
        model_id="glm-test",
        cost_input_per_m=2.0,
        cost_output_per_m=8.0,
        cost_cache_read_per_m=0.2,
        markup_rate=1.5,
        web_search_price_per_call=0.03,
    )
    defaults.update(kw)
    return PricingRule(**defaults)


def test_effective_prices_markup():
    prices = effective_prices(_rule())
    assert prices["input_per_m"] == Decimal("3.0")
    assert prices["output_per_m"] == Decimal("12.0")
    assert prices["cache_read_per_m"] == Decimal("0.3")


def test_effective_prices_missing_rule_is_zero():
    prices = effective_prices(None)
    assert all(v == Decimal("0") for v in prices.values())


def test_compute_costs_precision():
    # 1,000,000 input @ 3/M = 3.0；1,234,567 @ 12/M = 14.814804
    costs = compute_costs(1_000_000, 1_234_567, 0, 3, _rule())
    assert costs["cost_input"] == Decimal("3.000000")
    assert costs["cost_output"] == Decimal("14.814804")
    assert costs["cost_search"] == Decimal("0.090000")
    assert costs["cost_total"] == q6(
        costs["cost_input"] + costs["cost_output"] + costs["cost_cache"] + costs["cost_search"]
    )
    # 总额精确到 6 位小数，无浮点尾差
    assert str(costs["cost_total"]).split(".")[1].__len__() <= 6


def test_compute_costs_zero_deltas():
    costs = compute_costs(0, 0, 0, 0, _rule())
    assert costs["cost_total"] == Decimal("0.000000")


def test_small_amounts_no_rounding_to_zero():
    # 小量 token 也应产生非零费用（万级 token × 元级单价）
    costs = compute_costs(1000, 2000, 0, 0, _rule())
    assert costs["cost_input"] == Decimal("0.003000")
    assert costs["cost_output"] == Decimal("0.024000")
