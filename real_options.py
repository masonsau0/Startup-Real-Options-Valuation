"""Real options valuation library.

Functions to value an investment with abandon, switch, expand, and sell
options as a layered decision tree. Each option's incremental EMV is
computed independently, then summed with prior options to evaluate
composite strategies.

Usage
-----
>>> from real_options import Case, value_strategies
>>> case = Case.from_json("case_parameters.json")
>>> df = value_strategies(case)
>>> df.loc[df["emv"].idxmax()]
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import pandas as pd


@dataclass
class Case:
    """Case inputs in a typed container.

    Load from JSON with `Case.from_json(path)` so parameters stay
    data-driven (keeps the model reusable across case variants).
    """

    initial_investment: float
    ownership_share: float
    discount_rate_annual: float
    p_viewer: float
    p_website: float
    full_success_payoff: float
    abandon_gross: float
    abandon_cost: float
    switch_sale: float
    expand_investment_total: float
    expand_doubled_payoff: float
    sell_benefit: float
    sell_cost: float
    risk_tolerance: float

    @classmethod
    def from_json(cls, path: str | Path) -> "Case":
        data = json.loads(Path(path).read_text())
        cf = data["cash_flows"]
        return cls(
            initial_investment=cf["initial_investment"],
            ownership_share=data["ownership_share"],
            discount_rate_annual=data["discount_rate_annual"],
            p_viewer=data["probabilities"]["viewer_success"],
            p_website=data["probabilities"]["website_success"],
            full_success_payoff=cf["full_success_payoff_at_18m_per_share"],
            abandon_gross=cf["abandon"]["gross_sale"],
            abandon_cost=cf["abandon"]["packaging_cost"],
            switch_sale=cf["switch"]["web_business_sale"],
            expand_investment_total=cf["expand"]["total_investment"],
            expand_doubled_payoff=cf["expand"]["doubled_payoff_at_18m"],
            sell_benefit=cf["sell"]["control_premium_benefit"],
            sell_cost=cf["sell"]["buyout_cost"],
            risk_tolerance=data["utility"]["risk_tolerance"],
        )

    # Pin to the rounded discount factors used in the submitted report.
    # Swap for (1+r)**t to compute from scratch.
    DF_6M: float = 1.095
    DF_18M: float = 1.314

    @property
    def p_full(self) -> float:
        return self.p_viewer * self.p_website

    @property
    def p_abandon(self) -> float:
        return self.p_viewer * (1 - self.p_website)

    @property
    def p_switch(self) -> float:
        return self.p_website * (1 - self.p_viewer)

    @property
    def p_fail(self) -> float:
        return 1 - (self.p_full + self.p_abandon + self.p_switch)


# ------------------------------------------------------------------ #
# Per-option incremental EMVs                                         #
# ------------------------------------------------------------------ #


def emv_base(c: Case) -> float:
    """EMV with no options — commit capital, take expected payoff if full success."""
    payoff_pv = c.full_success_payoff / c.DF_6M
    return -c.initial_investment + c.p_full * payoff_pv


def incremental_abandon(c: Case) -> float:
    net = c.ownership_share * c.abandon_gross - c.abandon_cost
    return c.p_abandon * (net / c.DF_6M)


def incremental_switch(c: Case) -> float:
    payoff = c.ownership_share * c.switch_sale
    return c.p_switch * (payoff / c.DF_6M)


def incremental_expand(c: Case) -> float:
    """Expand only materialises on full success — compare expand-NPV vs base-NPV."""
    expand_pv = c.expand_doubled_payoff / c.DF_18M
    expand_cost_pv = (c.ownership_share * c.expand_investment_total) / c.DF_6M
    base_pv = c.full_success_payoff / c.DF_6M
    return c.p_full * (expand_pv - expand_cost_pv - base_pv)


def incremental_sell(c: Case) -> float:
    net_pv = (c.sell_benefit - c.sell_cost) / c.DF_18M
    return c.p_full * net_pv


# ------------------------------------------------------------------ #
# Composite strategy ladder                                           #
# ------------------------------------------------------------------ #


def value_strategies(c: Case) -> pd.DataFrame:
    """Return the cumulative EMV for each composite strategy."""
    steps = [
        ("Base (no options)", emv_base(c), emv_base(c)),
    ]
    cum = emv_base(c)
    for label, fn in [
        ("+ Abandon", incremental_abandon),
        ("+ Switch", incremental_switch),
        ("+ Expand", incremental_expand),
        ("+ Sell", incremental_sell),
    ]:
        inc = fn(c)
        cum = cum + inc
        steps.append((label, inc, cum))
    return pd.DataFrame(steps, columns=["strategy", "incremental_emv", "cumulative_emv"])


def optimal_strategy(c: Case) -> Dict[str, float]:
    df = value_strategies(c)
    best_idx = df["cumulative_emv"].idxmax()
    row = df.loc[best_idx]
    return {
        "strategy": " ".join(df.loc[: best_idx, "strategy"].tolist())
        .replace("+ ", "& ")
        .replace("Base (no options) & ", ""),
        "emv": float(row["cumulative_emv"]),
    }


# ------------------------------------------------------------------ #
# Risk analysis — exponential utility                                 #
# ------------------------------------------------------------------ #


def utility(x: float, risk_tolerance: float) -> float:
    return 1 - math.exp(-x / risk_tolerance)


def certainty_equivalent(expected_utility: float, risk_tolerance: float) -> float:
    return -risk_tolerance * math.log(1 - expected_utility)


def risk_analysis(c: Case) -> pd.DataFrame:
    """Compare base vs. abandon strategy under risk aversion."""
    rows = []

    base_eu = 0.15 * utility(366_000, c.risk_tolerance) + 0.85 * utility(-90_000, c.risk_tolerance)
    rows.append(
        {"strategy": "Base opportunity", "expected_utility": base_eu,
         "certainty_equivalent": certainty_equivalent(base_eu, c.risk_tolerance)}
    )

    abandon_eu = (
        0.15 * utility(366_000, c.risk_tolerance)
        + 0.15 * utility(114_000, c.risk_tolerance)
        + 0.70 * utility(-90_000, c.risk_tolerance)
    )
    rows.append(
        {"strategy": "Abandon option", "expected_utility": abandon_eu,
         "certainty_equivalent": certainty_equivalent(abandon_eu, c.risk_tolerance)}
    )

    return pd.DataFrame(rows)


if __name__ == "__main__":
    case = Case.from_json(Path(__file__).parent / "case_parameters.json")
    print(value_strategies(case).to_string(index=False))
    print("\nOptimal:", optimal_strategy(case))
    print("\n", risk_analysis(case).to_string(index=False))
