"""Static SVG charts for the PDF. Palette validated for the navy surface (see README):
series 1 Sea-Intelligence #3987e5, series 2 Xeneta #d95926."""

from __future__ import annotations

import io
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from port_brief import paths  # noqa: E402
from port_brief.sources.schedule_reliability import norm_carrier  # noqa: E402

SURFACE = "#0f1e2e"
INK = "#ffffff"
INK2 = "#c3cad3"
MUTED = "#8a96a3"
GRID = "#1e3044"
AXIS = "#2f455c"
SI = "#3987e5"
XE = "#d95926"

FONTS = paths.ROOT / "port_brief" / "render" / "fonts"
for _f in FONTS.glob("IBMPlexSans-*.ttf"):
    font_manager.fontManager.addfont(str(_f))

plt.rcParams.update({
    "font.family": "IBM Plex Sans", "font.size": 8.5, "text.color": INK2,
    "axes.edgecolor": AXIS, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.facecolor": SURFACE, "figure.facecolor": SURFACE, "svg.fonttype": "path",
})


def _period(p: str) -> str:
    from port_brief.render.issue import period_label

    return period_label(p)


def _svg(fig) -> str:
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.index("<svg"):]


def _style(ax):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def carrier_dumbbell(si: dict | None, xe: dict | None) -> str | None:
    if not si or not si.get("carriers"):
        return None
    xe_by = {norm_carrier(c["carrier"]): c["pct"] for c in (xe or {}).get("carriers", [])}
    rows = si["carriers"]
    fig, ax = plt.subplots(figsize=(4.6, 0.26 * len(rows) + 0.7))
    _style(ax)
    ys = list(range(len(rows)))[::-1]
    for y, c in zip(ys, rows):
        x2 = xe_by.get(norm_carrier(c["carrier"]))
        if x2 is not None:
            ax.plot([x2, c["pct"]], [y, y], color=AXIS, linewidth=2, solid_capstyle="round", zorder=1)
            ax.scatter([x2], [y], s=34, color=XE, edgecolor=SURFACE, linewidth=1.5, zorder=3)
        ax.scatter([c["pct"]], [y], s=34, color=SI, edgecolor=SURFACE, linewidth=1.5, zorder=3)
    ax.set_yticks(ys, [c["carrier"] for c in rows], color=INK2)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    ax.set_ylim(-0.7, len(rows) - 0.3)
    handles = [plt.Line2D([], [], marker="o", linestyle="", color=SI, markersize=6, label=f"Sea-Intelligence ({_period(si['period'])})")]
    if xe_by:
        handles.append(plt.Line2D([], [], marker="o", linestyle="", color=XE, markersize=6, label=f"Xeneta ({_period(xe['period'])})"))
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=2, frameon=False,
              fontsize=8, labelcolor=INK2, handletextpad=0.3, columnspacing=1.2)
    return _svg(fig)


def xeneta_history() -> dict[str, float]:
    out = {}
    for f in (paths.RELIABILITY / "xeneta").glob("20*-*.json"):
        rec = json.loads(f.read_text())
        if rec.get("global_pct") is not None and "Q" not in rec.get("period", "Q"):
            out[rec["period"]] = rec["global_pct"]
    return out


def global_trend(si: dict | None, months: int = 24) -> str | None:
    if not si or not si.get("series"):
        return None
    periods = sorted(si["series"])[-months:]
    xe = xeneta_history()
    fig, ax = plt.subplots(figsize=(4.6, 1.9))
    _style(ax)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.grid(axis="x", visible=False)
    xs = list(range(len(periods)))
    ax.plot(xs, [si["series"][p] for p in periods], color=SI, linewidth=2, label="Sea-Intelligence")
    ax.scatter([xs[-1]], [si["series"][periods[-1]]], s=34, color=SI, edgecolor=SURFACE, linewidth=1.5, zorder=3)
    ax.annotate(f"{si['series'][periods[-1]]}%", (xs[-1], si["series"][periods[-1]]), textcoords="offset points",
                xytext=(6, -3), color=INK, fontsize=8.5, fontweight="bold")
    xe_pts = [(xs[i], xe[p]) for i, p in enumerate(periods) if p in xe]
    if xe_pts:
        ax.plot([p[0] for p in xe_pts], [p[1] for p in xe_pts], color=XE, linewidth=2, marker="o", markersize=5,
                markeredgecolor=SURFACE, label="Xeneta")
        ax.annotate(f"{xe_pts[-1][1]}%", xe_pts[-1], textcoords="offset points", xytext=(6, -3), color=INK, fontsize=8.5, fontweight="bold")
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    ticks = [i for i, p in enumerate(periods) if p.endswith(("-01", "-07"))]
    ax.set_xticks(ticks, [periods[i][:4] if periods[i].endswith("-01") else "Jul" for i in ticks])
    ax.set_xlim(-0.5, len(periods) + 1.5)
    ax.legend(loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=2, frameon=False, fontsize=8, labelcolor=INK2)
    return _svg(fig)
