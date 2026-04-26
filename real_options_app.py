"""Interactive real-options valuation dashboard.

Run with::

    streamlit run real_options_app.py

Edit case parameters in the sidebar (probabilities, payoffs, discount rate,
risk tolerance) and watch the EMV ladder, optimal strategy, certainty
equivalents, and sensitivity sweeps update in real time.
"""

from __future__ import annotations

from dataclasses import replace

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from real_options import (
    Case,
    certainty_equivalent,
    emv_base,
    incremental_abandon,
    incremental_expand,
    incremental_sell,
    incremental_switch,
    optimal_strategy,
    risk_analysis,
    utility,
    value_strategies,
)

st.set_page_config(page_title="Real Options Valuation", layout="wide", page_icon="📈")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@st.cache_data
def base_case() -> Case:
    return Case.from_json("case_parameters.json")


def fmt(v: float) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.0f}"


# ---------------------------------------------------------------------------
# Sidebar — case parameters
# ---------------------------------------------------------------------------


st.title("Real Options Valuation Dashboard")
st.caption("Decision-tree EMV with abandon, switch, expand, and sell options under uncertainty.")

with st.expander("How to use this app", expanded=False):
    st.markdown("""
**What this app does in plain English.**
A startup is deciding whether to invest in a multi-stage software
project. There's uncertainty — the product might succeed or flop, the
market might shift. But the company has flexibility: at each decision
point, they can **abandon** the project, **switch** to a different
direction, **expand** if things go well, or **sell** the IP. Each of
these is called a "real option" (a real-world version of a financial
option). This app puts a dollar value on each option and finds the
combination that maximises **EMV** (Expected Monetary Value).

**Quick start (30 seconds).**
1. Check the **decision tree diagram** — it shows every path the
   project could take, with probabilities and cash flows.
2. The **EMV ladder** chart on the right shows what each strategy is
   worth — taller = more valuable.
3. Move the **probability sliders** in the sidebar to see how the
   recommendation shifts.

**The case parameters in the sidebar.**
- **Probability of success at each stage** — if the prototype phase
  succeeds with probability p, what's the value of continuing?
- **Cash flows** — investment costs and payoffs at each stage.
- **Discount rate** — to compare cash flows across years (a dollar
  today is worth more than a dollar in 5 years).
- **Risk aversion (utility curvature)** — for the certainty-equivalent
  view. A risk-averse founder values $50K guaranteed more than a
  50/50 shot at $100K — even though both have the same EMV.

**What the panels mean.**
- **Decision tree** — the full game tree of decisions and uncertainties.
  Squares = decisions, circles = chance nodes. The number at each leaf
  is the cash payoff if you reach that leaf.
- **EMV ladder** — bar chart comparing every composite strategy. The
  tallest bar is the recommendation.
- **Sensitivity analysis** — how does the optimal strategy change as
  the success probability varies from 30 % to 70 %? Helps you see if
  the recommendation is robust or fragile.

**Try this.** Drop the success probability of the second stage from
0.7 down to 0.4 and watch the recommended strategy switch from
"Expand" to "Abandon early" — that's the real-options framework
working: more uncertainty makes the abandon option more valuable.
""")

base = base_case()

with st.sidebar:
    st.header("Case parameters")

    if st.button("Reset to base case", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k.startswith("ro_"):
                del st.session_state[k]
        st.rerun()

    st.subheader("Investment")
    invest = st.number_input("Initial investment ($)", value=float(base.initial_investment), step=5000.0, key="ro_invest")
    share = st.number_input("Ownership share", value=float(base.ownership_share), min_value=0.0, max_value=1.0, step=0.05, key="ro_share")
    rate = st.slider("Discount rate (annual)", 0.0, 0.5, float(base.discount_rate_annual), 0.01, key="ro_rate")
    df6 = st.number_input("6-month discount factor", value=float(Case.DF_6M), step=0.001, format="%.4f",
                           help="Pinned to the report's rounded factor; uncheck below to compute from the rate.",
                           key="ro_df6")
    df18 = st.number_input("18-month discount factor", value=float(Case.DF_18M), step=0.001, format="%.4f", key="ro_df18")
    auto = st.checkbox("Compute discount factors from the annual rate", value=False, key="ro_auto")
    if auto:
        df6 = (1 + rate) ** 0.5
        df18 = (1 + rate) ** 1.5

    st.subheader("Probabilities")
    p_v = st.slider("P(viewer success)", 0.0, 1.0, float(base.p_viewer), 0.05, key="ro_pv")
    p_w = st.slider("P(website success)", 0.0, 1.0, float(base.p_website), 0.05, key="ro_pw")

    st.subheader("Cash flows ($)")
    full_payoff = st.number_input("Full success payoff (per share, t=18mo)", value=float(base.full_success_payoff), step=10000.0, key="ro_full")
    aban_g = st.number_input("Abandon — viewer gross sale", value=float(base.abandon_gross), step=10000.0, key="ro_ag")
    aban_c = st.number_input("Abandon — packaging cost", value=float(base.abandon_cost), step=1000.0, key="ro_ac")
    sw_sale = st.number_input("Switch — web business sale", value=float(base.switch_sale), step=10000.0, key="ro_sw")
    exp_inv = st.number_input("Expand — total investment", value=float(base.expand_investment_total), step=10000.0, key="ro_ei")
    exp_pay = st.number_input("Expand — doubled payoff (t=18mo)", value=float(base.expand_doubled_payoff), step=10000.0, key="ro_ep")
    sell_b = st.number_input("Sell — control premium benefit", value=float(base.sell_benefit), step=10000.0, key="ro_sb")
    sell_c = st.number_input("Sell — buyout cost", value=float(base.sell_cost), step=10000.0, key="ro_sc")

    st.subheader("Risk preferences")
    risk_tol = st.number_input("Exponential utility risk tolerance ($)",
                                value=float(base.risk_tolerance), step=5000.0,
                                help="u(x) = 1 - exp(-x / R). Smaller R = more risk-averse.",
                                key="ro_rt")


# Build a Case with the user's edits
case = replace(
    base,
    initial_investment=invest, ownership_share=share, discount_rate_annual=rate,
    p_viewer=p_v, p_website=p_w,
    full_success_payoff=full_payoff,
    abandon_gross=aban_g, abandon_cost=aban_c,
    switch_sale=sw_sale,
    expand_investment_total=exp_inv, expand_doubled_payoff=exp_pay,
    sell_benefit=sell_b, sell_cost=sell_c,
    risk_tolerance=risk_tol,
)
case.DF_6M = df6
case.DF_18M = df18


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

ladder = value_strategies(case)
best = optimal_strategy(case)

c1, c2, c3, c4 = st.columns(4)
c1.metric("P(full success)", f"{case.p_full:.2f}")
c2.metric("Optimal strategy", best["strategy"])
c3.metric("Optimal EMV", fmt(best["emv"]))
c4.metric("Δ vs. no options", fmt(best["emv"] - emv_base(case)))

st.divider()

tab_ladder, tab_risk, tab_sens, tab_tornado = st.tabs(
    ["EMV ladder", "Risk aversion", "Sensitivity sweep", "Tornado chart"]
)


# ---- EMV ladder -----------------------------------------------------------

with tab_ladder:
    cols = st.columns([1.2, 1])
    with cols[0]:
        fig, ax = plt.subplots(figsize=(7, 4))
        colors = ["#c44e52" if v < 0 else "#55a868" for v in ladder["cumulative_emv"]]
        ax.bar(ladder["strategy"], ladder["cumulative_emv"], color=colors)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_ylabel("Cumulative EMV ($)"); ax.set_title("Adding options sequentially")
        for i, v in enumerate(ladder["cumulative_emv"]):
            ax.text(i, v + (1500 if v > 0 else -3500), f"${v:,.0f}", ha="center", fontsize=8)
        plt.xticks(rotation=15, ha="right")
        st.pyplot(fig)
    with cols[1]:
        show = ladder.copy()
        show["incremental_emv"] = show["incremental_emv"].map(fmt)
        show["cumulative_emv"] = show["cumulative_emv"].map(fmt)
        st.dataframe(show, hide_index=True, use_container_width=True)
        st.markdown(
            f"**P(full)**  = {case.p_full:.2f}  \n"
            f"**P(abandon-path)**  = {case.p_abandon:.2f}  \n"
            f"**P(switch-path)**  = {case.p_switch:.2f}  \n"
            f"**P(fail)**  = {case.p_fail:.2f}"
        )


# ---- Risk aversion --------------------------------------------------------

with tab_risk:
    risk = risk_analysis(case)
    cols = st.columns([1, 1])
    with cols[0]:
        st.markdown(f"**Utility:** $u(x) = 1 - e^{{-x / {case.risk_tolerance:,.0f}}}$")
        show_risk = risk.copy()
        show_risk["expected_utility"] = show_risk["expected_utility"].map("{:.3f}".format)
        show_risk["certainty_equivalent"] = show_risk["certainty_equivalent"].map(fmt)
        st.dataframe(show_risk, hide_index=True, use_container_width=True)
        gap = risk.iloc[1]["certainty_equivalent"] - risk.iloc[0]["certainty_equivalent"]
        st.info(f"Abandon option lifts the certainty equivalent by **{fmt(gap)}** vs. the base opportunity — "
                f"the value of managerial flexibility under risk aversion.")

    with cols[1]:
        # Plot utility curve with CEs marked
        xs = np.linspace(-200_000, 400_000, 200)
        ys = [utility(x, case.risk_tolerance) for x in xs]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(xs, ys, color="#4c72b0")
        for _, row in risk.iterrows():
            ce = row["certainty_equivalent"]
            ax.axvline(ce, linestyle="--", alpha=0.6, color="#dd8452")
            ax.text(ce, 0.08, f" {row['strategy']}\n CE={fmt(ce)}", fontsize=8)
        ax.axhline(0, color="black", linewidth=0.4); ax.axvline(0, color="black", linewidth=0.4)
        ax.set_xlabel("payoff x ($)"); ax.set_ylabel("u(x)")
        ax.set_title("Exponential utility curve with certainty equivalents")
        ax.grid(alpha=0.3); st.pyplot(fig)


# ---- Sensitivity ----------------------------------------------------------

with tab_sens:
    st.markdown("Hold all parameters fixed except one; sweep that one across a plausible range and recompute the optimal-strategy EMV at each point.")
    feature = st.selectbox(
        "Parameter to sweep",
        ["P(viewer success)", "P(website success)", "Discount rate",
         "Initial investment", "Full success payoff"],
    )
    if feature == "P(viewer success)":
        grid = np.linspace(0.05, 0.95, 31); attr = "p_viewer"; fmt_x = "{:.2f}"
    elif feature == "P(website success)":
        grid = np.linspace(0.05, 0.95, 31); attr = "p_website"; fmt_x = "{:.2f}"
    elif feature == "Discount rate":
        grid = np.linspace(0.05, 0.50, 31); attr = "discount_rate_annual"; fmt_x = "{:.0%}"
    elif feature == "Initial investment":
        grid = np.linspace(40_000, 180_000, 29); attr = "initial_investment"; fmt_x = "${:,.0f}"
    else:
        grid = np.linspace(200_000, 1_000_000, 33); attr = "full_success_payoff"; fmt_x = "${:,.0f}"

    sweep = []
    for v in grid:
        alt = replace(case, **{attr: float(v)})
        if attr == "discount_rate_annual":
            alt.DF_6M = (1 + v) ** 0.5; alt.DF_18M = (1 + v) ** 1.5
        d = value_strategies(alt)
        sweep.append({"x": v, **{r["strategy"]: r["cumulative_emv"] for _, r in d.iterrows()}})
    sweep_df = pd.DataFrame(sweep)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for col in ["Base (no options)", "+ Abandon", "+ Switch", "+ Expand", "+ Sell"]:
        ax.plot(sweep_df["x"], sweep_df[col], label=col, linewidth=1.5)
    current_val = getattr(case, attr)
    ax.axvline(current_val, color="gray", linestyle="--", alpha=0.6, label=f"current ({fmt_x.format(current_val)})")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel(feature); ax.set_ylabel("Cumulative EMV ($)")
    ax.set_title(f"Strategy EMV vs. {feature}")
    ax.legend(); ax.grid(alpha=0.3)
    st.pyplot(fig)


# ---- Tornado --------------------------------------------------------------

with tab_tornado:
    st.markdown("Each parameter is varied ±20 % independently from its current value; the bars show the resulting change in the optimal-strategy EMV. Long bars mark the most leverage-y assumptions.")

    levers = [
        ("p_viewer", "P(viewer success)"),
        ("p_website", "P(website success)"),
        ("full_success_payoff", "Full success payoff"),
        ("initial_investment", "Initial investment"),
        ("abandon_gross", "Abandon gross sale"),
        ("switch_sale", "Switch — web business sale"),
        ("expand_doubled_payoff", "Expand — doubled payoff"),
        ("expand_investment_total", "Expand investment"),
    ]
    rows = []
    base_emv = optimal_strategy(case)["emv"]
    for attr, label in levers:
        v = getattr(case, attr)
        lo = replace(case, **{attr: v * 0.80}); lo_emv = optimal_strategy(lo)["emv"]
        hi = replace(case, **{attr: v * 1.20}); hi_emv = optimal_strategy(hi)["emv"]
        rows.append({"lever": label, "down20": lo_emv - base_emv, "up20": hi_emv - base_emv,
                     "abs_range": abs(hi_emv - lo_emv)})
    tor = pd.DataFrame(rows).sort_values("abs_range")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    y = np.arange(len(tor))
    ax.barh(y, tor["down20"], color="#c44e52", label="-20 %")
    ax.barh(y, tor["up20"], color="#55a868", label="+20 %")
    ax.set_yticks(y); ax.set_yticklabels(tor["lever"])
    ax.axvline(0, color="black", linewidth=0.5)
    ax.set_xlabel("Δ optimal EMV vs. base ($)")
    ax.set_title("Tornado — parameter sensitivity (±20 %)")
    ax.legend(); ax.grid(alpha=0.3, axis="x")
    st.pyplot(fig)
