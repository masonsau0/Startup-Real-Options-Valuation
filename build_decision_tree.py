"""Render a decision-tree diagram for the SCOR-eSTORE case.

Uses matplotlib only so it can run without graphviz. Writes decision_tree.png
to the current directory.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt


def _square(ax, xy, size=0.55, fc="#cfe2f3"):
    ax.add_patch(mpatches.FancyBboxPatch(
        (xy[0] - size / 2, xy[1] - size / 2), size, size,
        boxstyle="round,pad=0.02", fc=fc, ec="black", linewidth=1.1))


def _circle(ax, xy, r=0.28, fc="#d9ead3"):
    ax.add_patch(mpatches.Circle(xy, r, fc=fc, ec="black", linewidth=1.1))


def _text(ax, xy, s, fontsize=8.5, weight="normal"):
    ax.text(xy[0], xy[1], s, ha="center", va="center", fontsize=fontsize, weight=weight)


def _edge(ax, p0, p1, label="", above=True, fontsize=7.5):
    ax.annotate("", xy=p1, xytext=p0, arrowprops=dict(arrowstyle="-", linewidth=0.9))
    if label:
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        ax.text(mx, my + (0.14 if above else -0.14), label,
                ha="center", va="center", fontsize=fontsize, color="#333")


def main():
    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.set_xlim(-0.3, 12); ax.set_ylim(-0.5, 6); ax.axis("off")

    # Level 0: invest decision
    n0 = (0.6, 3)
    _square(ax, n0); _text(ax, (n0[0], n0[1] + 0.45), "Invest?", weight="bold")

    # No branch
    n_no = (1.6, 4.6)
    _edge(ax, n0, n_no, "No")
    _text(ax, n_no, "Payoff = $0")

    # Yes branch to viewer chance node
    n1 = (2.4, 2.6); _circle(ax, n1); _text(ax, n1, "V?")
    _edge(ax, n0, n1, "Yes, -$90k", above=False)

    # Viewer No branch -> Website chance
    n2 = (4.2, 4.3); _circle(ax, n2); _text(ax, n2, "W?")
    _edge(ax, n1, n2, "p=0.7 (no)")

    # Website No (both fail): payoff 0
    n3 = (5.6, 5.4); _edge(ax, n2, n3, "p=0.5 (no)"); _text(ax, n3, "Payoff = $0")

    # Website Yes (Switch exercised)
    n4 = (5.6, 3.6); _edge(ax, n2, n4, "p=0.5 Switch"); _text(ax, n4, "Payoff ≈ $91k")

    # Viewer Yes -> Website chance
    n5 = (4.2, 1.2); _circle(ax, n5); _text(ax, n5, "W?")
    _edge(ax, n1, n5, "p=0.3 (yes)", above=False)

    # Website No -> Abandon decision
    n6 = (5.8, 2.2); _square(ax, n6, fc="#fce5cd"); _text(ax, n6, "Abandon", fontsize=7.5, weight="bold")
    _edge(ax, n5, n6, "p=0.5 (no)")

    n6a = (7.0, 2.9); _edge(ax, n6, n6a, "Yes"); _text(ax, n6a, "Payoff ≈ $114k")
    n6b = (7.0, 1.5); _edge(ax, n6, n6b, "No", above=False); _text(ax, n6b, "Payoff = $0")

    # Website Yes (full success) -> Expand decision
    n7 = (5.8, 0.2); _square(ax, n7, fc="#fce5cd"); _text(ax, n7, "Expand?", fontsize=7.5, weight="bold")
    _edge(ax, n5, n7, "p=0.5 (yes)", above=False)

    # Expand No -> Sell decision
    n8 = (7.2, -0.2); _square(ax, n8, fc="#fce5cd"); _text(ax, n8, "Sell?", fontsize=7.5, weight="bold")
    _edge(ax, n7, n8, "No", above=False)
    n8a = (8.6, 0.35); _edge(ax, n8, n8a, "No"); _text(ax, n8a, "Payoff ≈ $456k")
    n8b = (8.6, -0.9); _edge(ax, n8, n8b, "Yes", above=False); _text(ax, n8b, "Payoff ≈ $380k")

    # Expand Yes -> Sell decision
    n9 = (7.2, 0.8); _square(ax, n9, fc="#fce5cd"); _text(ax, n9, "Sell?", fontsize=7.5, weight="bold")
    _edge(ax, n7, n9, "Yes  -1/3·$450k")
    n9a = (8.6, 1.4); _edge(ax, n9, n9a, "No"); _text(ax, n9a, "Payoff ≈ $623k")
    n9b = (8.6, 0.2); _edge(ax, n9, n9b, "Yes", above=False); _text(ax, n9b, "Payoff ≈ $547k")

    # Legend
    legend_sq = mpatches.Patch(fc="#cfe2f3", ec="black", label="Decision node (initial)")
    legend_sq2 = mpatches.Patch(fc="#fce5cd", ec="black", label="Real-options decision")
    legend_c = mpatches.Patch(fc="#d9ead3", ec="black", label="Chance node")
    ax.legend(handles=[legend_sq, legend_sq2, legend_c], loc="lower left", fontsize=8, frameon=False)

    ax.set_title("SCOR-eSTORE.COM — Real options decision tree", fontsize=11, weight="bold")
    plt.tight_layout()
    plt.savefig("decision_tree.png", dpi=130, bbox_inches="tight")
    print("Wrote decision_tree.png")


if __name__ == "__main__":
    main()
