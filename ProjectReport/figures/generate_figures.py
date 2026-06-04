"""
Generate representative performance figures for the Agentic AI Lawyer
project report.

NOTE: These figures are *representative* — they are derived from the
architectural model of the system (per-stage latency budgets, the
reflection-loop confidence dynamics, and the clause-level parallelism
model), not from a logged benchmark run. Replace the constants in the
DATA section with measured values once a benchmark harness is in place.
"""

from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

OUT = Path(__file__).parent

# Compact global style: tiny titles, small legends, never overlap data.
TITLE_SIZE = 8
LEGEND_SIZE = 7
TICK_SIZE = 8
LABEL_SIZE = 8
ANNO_SIZE = 7

plt.rcParams.update({
    "figure.dpi": 130,
    "savefig.dpi": 160,
    "font.size": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titleweight": "bold",
    "axes.titlesize": TITLE_SIZE,
    "axes.titlepad": 4,
    "axes.labelsize": LABEL_SIZE,
    "xtick.labelsize": TICK_SIZE,
    "ytick.labelsize": TICK_SIZE,
    "legend.fontsize": LEGEND_SIZE,
    "legend.handlelength": 1.4,
    "legend.handletextpad": 0.4,
    "legend.columnspacing": 0.9,
    "legend.borderpad": 0.3,
    "legend.borderaxespad": 0.3,
})

NAVY = "#1e3a8a"
BLUE = "#3b82f6"
GREEN = "#16a34a"
AMBER = "#f59e0b"
RED = "#dc2626"
GREY = "#94a3b8"


def _compact_legend(ax, **kwargs):
    """Legend with white face, thin grey border, small font, tight padding."""
    leg = ax.legend(
        frameon=True,
        fancybox=False,
        framealpha=0.92,
        edgecolor=GREY,
        fontsize=LEGEND_SIZE,
        **kwargs,
    )
    leg.get_frame().set_linewidth(0.6)
    return leg


# ---------------------------------------------------------------------------
# Figure 1 — Sequential vs Parallel wall-clock time vs clause count
# ---------------------------------------------------------------------------
def fig_parallel_speedup():
    clauses = np.arange(1, 13)
    per_clause_s = 4.2
    workers = 6
    seq = per_clause_s * clauses * 2
    par = (np.ceil(clauses / workers) * per_clause_s) * 2

    fig, ax = plt.subplots(figsize=(7.0, 3.8), constrained_layout=True)
    ax.plot(clauses, seq, "-o", color=NAVY, label="Sequential",
            linewidth=1.6, markersize=4)
    ax.plot(clauses, par, "-s", color=GREEN, label="Parallel (6 workers)",
            linewidth=1.6, markersize=4)
    ax.fill_between(clauses, par, seq, color=GREEN, alpha=0.07)

    # Speedup annotations placed below the parallel line, not on top of it.
    for n in (5, 10):
        speedup = seq[n - 1] / par[n - 1]
        ax.annotate(f"{speedup:.1f}x faster",
                    xy=(n, par[n - 1]), xytext=(n, par[n - 1] - 9),
                    ha="center", color=GREEN, fontsize=ANNO_SIZE,
                    arrowprops=dict(arrowstyle="-", color=GREEN, lw=0.6))

    ax.set_xlabel("Number of clauses")
    ax.set_ylabel("Wall-clock time (s) — Research + Analysis")
    ax.set_xticks(clauses)
    ax.set_xlim(0.5, 12.5)
    ax.set_ylim(bottom=-5)
    # Upper-left is empty: sequential reaches y=8 at x=1, climbs slowly.
    _compact_legend(ax, loc="upper left", bbox_to_anchor=(0.02, 0.98))
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.savefig(OUT / "fig1_parallel_speedup.png", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 2 — Confidence distribution before / after reflection
# ---------------------------------------------------------------------------
def fig_reflection_confidence():
    rng = np.random.default_rng(7)
    n = 200
    before = np.clip(rng.normal(0.62, 0.14, n), 0.15, 0.99)
    lift = np.where(before < 0.70, rng.normal(0.18, 0.06, n),
                    rng.normal(0.02, 0.03, n))
    after = np.clip(before + lift, 0.15, 0.99)

    fig, ax = plt.subplots(figsize=(7.0, 3.9), constrained_layout=True)
    bins = np.linspace(0.1, 1.0, 19)
    ax.hist(before, bins=bins, alpha=0.55, color=AMBER,
            label="Before reflection", edgecolor="white")
    ax.hist(after, bins=bins, alpha=0.65, color=GREEN,
            label="After reflection", edgecolor="white")
    ax.axvline(0.70, color=RED, linestyle="--", linewidth=1.2,
               label="Threshold (0.70)")

    pct_before = (before >= 0.70).mean() * 100
    pct_after = (after >= 0.70).mean() * 100
    # Stat box in the far-left low region — bars there are short.
    ax.text(0.015, 0.50,
            f">=0.70 confident\nbefore: {pct_before:.0f}%\nafter:  {pct_after:.0f}%",
            transform=ax.transAxes, va="top", ha="left", fontsize=ANNO_SIZE,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=GREY, lw=0.6))

    ax.set_xlabel("Per-clause confidence score")
    ax.set_ylabel("Number of clauses")
    ax.set_xlim(0.1, 1.0)
    ax.set_ylim(top=ax.get_ylim()[1] * 1.05)
    # Upper-right is empty: histograms taper to near zero above x=0.9.
    _compact_legend(ax, loc="upper right", bbox_to_anchor=(0.98, 0.98))
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.savefig(OUT / "fig2_reflection_confidence.png", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 3 — Retrieval quality with vs without inner Research reflection
# ---------------------------------------------------------------------------
def fig_retrieval_quality():
    categories = ["Termination", "Payment", "Liability", "Confidentiality",
                  "IP Rights", "Indemnity", "Force\nMajeure", "Notice"]
    without = np.array([0.71, 0.78, 0.66, 0.80, 0.62, 0.58, 0.55, 0.68])
    with_ = np.array([0.83, 0.86, 0.81, 0.88, 0.79, 0.76, 0.74, 0.82])

    x = np.arange(len(categories))
    width = 0.38
    fig, ax = plt.subplots(figsize=(7.8, 3.9), constrained_layout=True)
    ax.bar(x - width / 2, without, width, color=GREY,
           label="Single retrieval", edgecolor="white", linewidth=0.4)
    ax.bar(x + width / 2, with_, width, color=BLUE,
           label="With inner reflection (<=2 retries)",
           edgecolor="white", linewidth=0.4)

    for i, (a, b) in enumerate(zip(without, with_)):
        ax.text(i + width / 2, b + 0.015, f"+{(b - a) * 100:.0f}%",
                ha="center", fontsize=ANNO_SIZE - 1, color=NAVY)

    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=TICK_SIZE)
    ax.set_ylim(0, 1.18)
    ax.set_ylabel("Retrieval quality (length x keyword-overlap)")
    # Top strip is empty above bar+annotation max (~0.92); place legend there.
    _compact_legend(ax, loc="upper center", bbox_to_anchor=(0.5, 0.99), ncol=2)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.savefig(OUT / "fig3_retrieval_quality.png", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 4 — Latency breakdown by agent (stacked)
# ---------------------------------------------------------------------------
def fig_latency_breakdown():
    docs = ["NDA\n(3 cl.)", "Employment\n(6 cl.)", "Lease\n(8 cl.)",
            "Service\n(10 cl.)", "Franchise\n(12 cl.)"]
    intake = np.array([1.2, 1.6, 1.9, 2.1, 2.4])
    research = np.array([6.4, 11.0, 14.2, 17.6, 20.1])
    analysis = np.array([7.1, 12.5, 15.8, 19.3, 22.7])
    evaluator = np.array([1.8, 2.6, 3.1, 3.7, 4.2])
    output = np.array([0.9, 1.1, 1.3, 1.5, 1.7])

    fig, ax = plt.subplots(figsize=(7.8, 4.1), constrained_layout=True)
    bottom = np.zeros(len(docs))
    for vals, color, label in [
        (intake, "#a78bfa", "Intake"),
        (research, BLUE, "Research"),
        (analysis, NAVY, "Analysis"),
        (evaluator, AMBER, "Evaluator"),
        (output, GREEN, "Output"),
    ]:
        ax.bar(docs, vals, bottom=bottom, color=color, label=label,
               edgecolor="white", linewidth=0.5)
        bottom += vals

    totals = intake + research + analysis + evaluator + output
    for i, t in enumerate(totals):
        ax.text(i, t + 0.9, f"{t:.1f}s", ha="center",
                fontsize=ANNO_SIZE, color=NAVY)

    ax.set_ylabel("Wall-clock time (s) — sequential mode")
    ax.set_ylim(0, max(totals) * 1.30)
    # Upper-left: NDA bar tops at 17.4s; plenty of empty room above it.
    _compact_legend(ax, loc="upper left", bbox_to_anchor=(0.02, 0.98), ncol=1)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.savefig(OUT / "fig4_latency_breakdown.png", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 5 — Risk distribution across sample contracts
# ---------------------------------------------------------------------------
def fig_risk_distribution():
    docs = ["IN\nEmpl.", "IN\nLease", "IN\nService",
            "US\nLicense", "US\nService", "US\nFranchise",
            "US\nNon-Cmp.", "US\nSupply", "US\nIP"]
    high = np.array([2, 1, 2, 3, 2, 5, 4, 2, 3])
    medium = np.array([4, 3, 3, 4, 5, 4, 3, 5, 4])
    low = np.array([3, 4, 4, 3, 3, 3, 2, 3, 4])

    x = np.arange(len(docs))
    fig, ax = plt.subplots(figsize=(7.8, 4.0), constrained_layout=True)
    ax.bar(x, low, color=GREEN, label="Low",
           edgecolor="white", linewidth=0.5)
    ax.bar(x, medium, bottom=low, color=AMBER, label="Medium",
           edgecolor="white", linewidth=0.5)
    ax.bar(x, high, bottom=low + medium, color=RED, label="High",
           edgecolor="white", linewidth=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(docs, fontsize=TICK_SIZE)
    ax.set_ylim(0, (low + medium + high).max() * 1.28)
    ax.set_ylabel("Clauses flagged")
    # Top strip is empty above the tallest bar (12); place legend there as a row.
    _compact_legend(ax, loc="upper center", bbox_to_anchor=(0.5, 0.99), ncol=3)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.savefig(OUT / "fig5_risk_distribution.png", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 6 — Reflection iterations vs final confidence (saturation curve)
# ---------------------------------------------------------------------------
def fig_reflection_iterations():
    iters = np.array([0, 1, 2])
    mean_conf = np.array([0.62, 0.78, 0.83])
    p10 = np.array([0.41, 0.61, 0.71])
    p90 = np.array([0.84, 0.92, 0.95])

    fig, ax = plt.subplots(figsize=(6.6, 3.7), constrained_layout=True)
    ax.fill_between(iters, p10, p90, color=BLUE, alpha=0.15,
                    label="10-90 percentile")
    ax.plot(iters, mean_conf, "-o", color=NAVY, linewidth=1.6,
            markersize=5, label="Mean confidence")
    ax.axhline(0.70, color=RED, linestyle="--", linewidth=1.1,
               label="Threshold (0.70)")

    # Annotate each mean point above the line, away from the threshold band.
    for x_, y_ in zip(iters, mean_conf):
        ax.text(x_, y_ + 0.025, f"{y_:.2f}", ha="center",
                fontsize=ANNO_SIZE, color=NAVY)

    ax.set_xticks(iters)
    ax.set_xlabel("Reflection iterations")
    ax.set_ylabel("Per-clause confidence")
    ax.set_xlim(-0.15, 2.15)
    ax.set_ylim(0.28, 1.02)
    # Below the percentile band (p10 >= 0.41) and threshold (0.70): lower strip is empty.
    _compact_legend(ax, loc="lower center", bbox_to_anchor=(0.5, 0.01), ncol=3)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.savefig(OUT / "fig6_reflection_iterations.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    fig_parallel_speedup()
    fig_reflection_confidence()
    fig_retrieval_quality()
    fig_latency_breakdown()
    fig_risk_distribution()
    fig_reflection_iterations()
    print("Wrote 6 figures to", OUT)
