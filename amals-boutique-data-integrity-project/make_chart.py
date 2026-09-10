import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

with open("metrics_summary.json") as f:
    m = json.load(f)

before = m["before_flagged_total"]
after = m["after_audit"]["master_records_with_any_issue"]
pct = m["discrepancy_reduction_pct"]

BRAND = "#33433C"
ACCENT = "#A65D6E"
GRAY = "#95A5A6"

fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=200)
fig.patch.set_facecolor("white")
ax.set_facecolor("white")

bars = ax.bar(
    ["Before\n(3 raw sources)", "After\n(centralized master)"],
    [before, after],
    color=[ACCENT, BRAND],
    width=0.5,
    zorder=3,
)
for rect, val in zip(bars, [before, after]):
    ax.annotate(f"{val:,}", (rect.get_x() + rect.get_width() / 2, rect.get_height()),
                textcoords="offset points", xytext=(0, 8), ha="center",
                fontsize=13, fontweight="bold", color="#25302B")

ax.set_ylabel("Flagged data-integrity issues", fontsize=10.5, color="#3F4A45")
ax.set_title(f"Data-integrity issues, before vs. after consolidation\n−{pct:.0f}% reduction",
             fontsize=13, fontweight="bold", color="#25302B", pad=14)
ax.spines[["top", "right"]].set_visible(False)
ax.spines[["left", "bottom"]].set_color(GRAY)
ax.tick_params(colors="#3F4A45", labelsize=10.5)
ax.yaxis.grid(True, color="#E3E6E2", zorder=0)
ax.set_ylim(0, before * 1.18)

plt.tight_layout()
plt.savefig("before_after_chart.png", facecolor="white")
print("Saved before_after_chart.png")
