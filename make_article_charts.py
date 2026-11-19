"""
Article graphics for the NBA Mercy Rule post.

Reads the outputs of main.py (run with --historical so NBA.com's official
team ratings are cached) and writes PNGs to output/article_charts/.

    python make_article_charts.py
"""

from __future__ import annotations

import glob
from pathlib import Path

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch, Rectangle

OUT = Path("output")
CHARTS = OUT / "article_charts"

# Palette (validated: blue/orange and blue/red pass all CVD checks).
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#ebeae4"
AXIS = "#c3c2b7"
BLUE = "#2a78d6"
BLUE_LIGHT = "#b7d3f6"
ORANGE = "#eb6834"
RED = "#e34948"
BEFORE = "#c9c8c0"

FONT = "Segoe UI"
FONT_BOLD = "Segoe UI Semibold"
SOURCE = "Data: NBA.com play-by-play, 2015-16 to 2025-26 regular seasons"

SHORT = {
    "Oklahoma City Thunder": "Thunder", "Golden State Warriors": "Warriors",
    "Portland Trail Blazers": "Trail Blazers", "Minnesota Timberwolves": "Timberwolves",
    "New Orleans Pelicans": "Pelicans", "Los Angeles Lakers": "Lakers",
    "LA Clippers": "Clippers", "San Antonio Spurs": "Spurs",
}

plt.rcParams.update({
    "figure.dpi": 200,  # measure text at the resolution it is saved at
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.family": [FONT, "DejaVu Sans"],
    "font.size": 12,
    "text.color": INK,
    "axes.labelcolor": MUTED,
    "axes.labelsize": 11,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "axes.edgecolor": AXIS,
})


def label(row):
    return f"{row.season} {SHORT.get(row.team, row.team.split()[-1])}"


def frame(title, subtitle=None, figsize=(10, 5.6), left=0.08):
    fig, ax = plt.subplots(figsize=figsize)
    fig.subplots_adjust(left=left, right=0.95, top=0.80, bottom=0.14)
    fig.text(0.05, 0.92, title, fontsize=21, fontname=FONT_BOLD, color=INK)
    if subtitle:
        fig.text(0.05, 0.865, subtitle, fontsize=12.5, color=INK_2)
    fig.text(0.05, 0.035, SOURCE, fontsize=9, color=MUTED)
    ax.tick_params(length=0, pad=8)
    return fig, ax


def legend_line(fig, parts, y=0.865, x=0.05, size=12.5):
    """Subtitle made of (text, color, bold) pieces, so it doubles as a legend."""
    renderer = fig.canvas.get_renderer()

    def width(s, font):
        t = fig.text(0, 0, s, fontsize=size, fontname=font)
        w = t.get_window_extent(renderer).width / fig.bbox.width
        t.remove()
        return w

    space = width("a a", FONT) - width("aa", FONT)
    for text, color, bold in parts:
        font = FONT_BOLD if bold else FONT
        lead = len(text) - len(text.lstrip(" "))
        trail = len(text) - len(text.rstrip(" "))
        x += lead * space
        if text.strip() == "●":
            fig.add_artist(plt.Line2D([x + space * 0.6], [y + 0.012], marker="o",
                                      markersize=11, color=color, transform=fig.transFigure))
            x += space * 2.2
        else:
            fig.text(x, y, text.strip(), fontsize=size, color=color, fontname=font)
            x += width(text.strip(), font)
        x += trail * space


def grid(ax, axis="y"):
    ax.grid(True, axis=axis, color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def rounded_bars(ax, positions, values, width, colors, horizontal=False, radius=7):
    """Bars with rounded data-ends and a square base on the zero line."""
    fig = ax.figure
    fig.canvas.draw()
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    px_x = ax.bbox.width / (x1 - x0)
    px_y = ax.bbox.height / (y1 - y0)
    rx, ry = radius / px_x, radius / px_y
    for pos, val, color in zip(positions, values, colors):
        if val == 0:
            continue
        sign = 1 if val > 0 else -1
        # Draw the rounded box past the baseline, then clip it at the
        # baseline, so only the data end is rounded and there is no seam.
        if horizontal:
            x, y = (-rx if sign > 0 else val), pos - width / 2
            w, h = abs(val) + rx, width
            clip = Rectangle((min(0, val), y - 1), abs(val), width + 2,
                             transform=ax.transData)
        else:
            x, y = pos - width / 2, (-ry if sign > 0 else val)
            w, h = width, abs(val) + ry
            clip = Rectangle((x - 1, min(0, val)), width + 2, abs(val),
                             transform=ax.transData)
        patch = FancyBboxPatch(
            (x, y), w, h, boxstyle=f"round,pad=0,rounding_size={rx}",
            mutation_aspect=ry / rx, color=color, linewidth=0)
        ax.add_patch(patch)
        patch.set_clip_path(clip)


def save(fig, name):
    fig.savefig(CHARTS / name, dpi=200)
    plt.close(fig)
    print("wrote", CHARTS / name)


# ---------------------------------------------------------------------------

def blowout_shares():
    rows = []
    for path in sorted(glob.glob("data/cache/schedule_*_Regular_Season.csv")):
        season = Path(path).name.split("_")[1]
        d = pd.read_csv(path)
        margin = d[d.PLUS_MINUS > 0].drop_duplicates("GAME_ID").PLUS_MINUS
        rows.append({"season": season,
                     "p20": 100 * (margin >= 20).mean(),
                     "p30": 100 * (margin >= 30).mean()})
    return pd.DataFrame(rows)


def chart_games_cut(scen):
    fig, ax = frame("Nearly 1 in 3 games would have ended early",
                    "Share of NBA games a mercy rule would have cut short")
    n = len(scen)
    ax.set_xlim(-0.6, n - 0.4)
    ax.set_ylim(0, 36)
    ax.set_yticks([0, 10, 20, 30])
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.set_xticks(range(n), [s[2:] for s in scen.season])
    grid(ax)
    colors = [BLUE_LIGHT] * (n - 1) + [BLUE]
    rounded_bars(ax, range(n), scen.pct_games_cut, 0.68, colors)
    for i in (0, n - 1):
        pct = scen.pct_games_cut.iloc[i]
        ax.text(i, pct + 0.9, f"{pct:.1f}%", ha="center", fontsize=13,
                fontname=FONT_BOLD, color=INK)
    save(fig, "01_games_cut_by_season.png")


def chart_blowouts(blow):
    fig, ax = frame("Blowouts are on the rise")
    legend_line(fig, [("Share of games decided by ", INK_2, False),
                      ("20+", BLUE, True), (" and ", INK_2, False),
                      ("30+ points", ORANGE, True)])
    x = list(range(len(blow)))
    for col, color in (("p20", BLUE), ("p30", ORANGE)):
        ax.plot(x, blow[col], color=color, linewidth=2.6, solid_capstyle="round")
        ax.scatter([x[0], x[-1]], [blow[col].iloc[0], blow[col].iloc[-1]],
                   s=70, color=color, edgecolor=SURFACE, linewidth=2, zorder=3)
        ax.text(x[-1] + 0.3, blow[col].iloc[-1], f"{blow[col].iloc[-1]:.1f}%",
                va="center", fontsize=14, fontname=FONT_BOLD, color=INK)
        ax.text(x[0] - 0.3, blow[col].iloc[0], f"{blow[col].iloc[0]:.1f}%",
                va="center", ha="right", fontsize=11, color=INK_2)
    ax.set_xticks(x, [s[2:] for s in blow.season])
    ax.set_xlim(-1.3, len(x) + 0.6)
    ax.set_ylim(0, 26)
    ax.set_yticks([0, 5, 10, 15, 20, 25])
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    grid(ax)
    save(fig, "02_blowout_trend.png")


def chart_no_comebacks(games):
    cut = games[games.triggered == True].copy()  # noqa: E712
    margin = (cut.actual_home - cut.actual_away).abs()
    fig, ax = frame(f"{len(cut):,} games cut short. Zero comebacks.",
                    "Final margin of every game the mercy rule would have ended")
    fig.subplots_adjust(bottom=0.19)
    counts = margin.groupby((margin // 2) * 2).size()
    ax.set_xlim(-2, 66)
    ax.set_ylim(0, counts.max() * 1.12)
    ax.set_xticks([0, 10, 20, 30, 40, 50, 60])
    ax.set_xlabel("Final margin (points)", labelpad=8)
    grid(ax)
    rounded_bars(ax, counts.index + 1, counts.values, 1.6, [BLUE] * len(counts), radius=4)
    ax.axvline(0, color=RED, linewidth=2.5, solid_capstyle="round")
    ax.text(1, counts.max() * 1.05, "Comeback", color=RED, fontsize=11.5,
            fontname=FONT_BOLD, va="center")
    closest = int(margin.min())
    ax.annotate(f"Closest: {closest} pts", xy=(closest, 0), xytext=(closest, counts.max() * 0.22),
                ha="center", fontsize=11, color=INK_2,
                arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=1, shrinkA=4, shrinkB=0))
    save(fig, "03_zero_comebacks.png")


def chart_net_changes(ratings):
    top = ratings.nlargest(6, "delta_net")
    bottom = ratings.nsmallest(6, "delta_net")
    data = pd.concat([bottom.iloc[::-1], top.iloc[::-1]]).reset_index(drop=True)
    pos = [i + (0.6 if i >= 6 else 0) for i in range(len(data))]
    fig, ax = frame("Good teams get better. Bad teams get worse.",
                    "Biggest net rating changes once garbage time is removed",
                    figsize=(10, 6.4), left=0.22)
    ax.set_xlim(-1.55, 1.55)
    ax.set_ylim(-0.7, pos[-1] + 0.7)
    ax.set_yticks(pos, [label(r) for r in data.itertuples()], color=INK, fontsize=11.5)
    ax.set_xticks([-1, -0.5, 0, 0.5, 1], ["−1.0", "−0.5", "0", "+0.5", "+1.0"])
    grid(ax, "x")
    ax.spines["bottom"].set_visible(False)
    colors = [BLUE if v > 0 else RED for v in data.delta_net]
    rounded_bars(ax, pos, data.delta_net, 0.66, colors, horizontal=True, radius=6)
    ax.axvline(0, color=AXIS, linewidth=1.2)
    for p, v in zip(pos, data.delta_net):
        ax.text(v + (0.05 if v > 0 else -0.05), p, f"{v:+.1f}".replace("-", "−"),
                ha="left" if v > 0 else "right", va="center",
                fontsize=11.5, fontname=FONT_BOLD, color=INK)
    save(fig, "04_net_rating_changes.png")


def dumbbell(data, before, after, title, xlabel, name, subtitle=None):
    data = data.iloc[::-1]
    fig, ax = frame(title, subtitle, figsize=(10, 5.8 + 0.4 * max(0, len(data) - 7)), left=0.25)
    fig.subplots_adjust(bottom=0.18)
    legend_line(fig, [("●", BEFORE, False), (" Actual    ", INK_2, False),
                      ("●", BLUE, False), (" Garbage time removed", INK_2, False)])
    y = list(range(len(data)))
    for i, (b, a) in enumerate(zip(data[before], data[after])):
        ax.plot([b, a], [i, i], color=BEFORE, linewidth=3, solid_capstyle="round", zorder=1)
    ax.scatter(data[before], y, s=110, color=BEFORE, zorder=2, edgecolor=SURFACE, linewidth=2)
    ax.scatter(data[after], y, s=150, color=BLUE, zorder=3, edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(y, [f"{r.rank_after}.  {label(r)}" for r in data.itertuples()],
                  color=INK, fontsize=12)
    for i, (b, a) in enumerate(zip(data[before], data[after])):
        change = round(a - b, 1)
        text = "no change" if change == 0 else f"{change:+.1f}".replace("-", "−")
        ax.text(max(a, b) + 0.07, i, text, va="center", fontsize=11.5,
                fontname=FONT_BOLD, color=MUTED if change == 0 else BLUE)
    lo = min(data[before].min(), data[after].min())
    hi = max(data[before].max(), data[after].max())
    ax.set_xlim(lo - 0.35, hi + 0.45)
    ax.set_ylim(-0.6, len(data) - 0.4)
    ax.xaxis.set_major_formatter(lambda v, _: f"+{v:.1f}")
    ax.set_xlabel(xlabel, labelpad=8)
    ax.spines["bottom"].set_visible(False)
    grid(ax, "x")
    save(fig, name)


def chart_top_units(ratings):
    r = ratings.copy()
    lg_a = r.groupby("season").apply(
        lambda x: 100 * x.actual_pts.sum() / x.actual_poss.sum(), include_groups=False)
    lg_m = r.groupby("season").apply(
        lambda x: 100 * x.mercy_pts.sum() / x.mercy_poss.sum(), include_groups=False)
    # Offense and defense on NBA.com's official base, like the tables (10/11):
    # after = official rating + our play-by-play change, against a league
    # average shifted by the same play-by-play change.
    o = official_ratings()
    r = r.merge(o[["season", "TEAM_NAME", "OFF_RATING", "DEF_RATING",
                   "LG_OFF_RATING", "LG_DEF_RATING"]],
                left_on=["season", "team"], right_on=["season", "TEAM_NAME"], how="left")
    if r.OFF_RATING.isna().any():
        raise ValueError("Team names did not match the official ratings")
    shift = r.season.map(lg_m) - r.season.map(lg_a)
    r["off_a"] = r.OFF_RATING - r.LG_OFF_RATING
    r["off_m"] = (r.OFF_RATING + r.mercy_ortg - r.actual_ortg) - (r.LG_OFF_RATING + shift)
    # Defense flipped so that "better than average" is positive / to the right.
    r["def_a"] = r.LG_DEF_RATING - r.DEF_RATING
    r["def_m"] = (r.LG_DEF_RATING + shift) - (r.DEF_RATING + r.mercy_drtg - r.actual_drtg)

    # Net rating on NBA.com's official base (it is comparable across seasons),
    # so the chart matches nba.com/stats and team_ratings_2015-2026.csv.
    official = pd.read_csv(OUT / "team_ratings_2015-2026.csv").set_index(["Season", "Team"])
    key = list(zip(r.season, r.team))
    r["net_a"] = official.reindex(key)["NetRtg"].to_numpy()
    r["net_m"] = r.net_a + r.delta_net
    chart_three_ratings(r)
    chart_best_net(r)
    chart_best_net(r, worst=True)

    panels = []
    for side, title, xlabel, name in (
        ("off", "The best offenses of the decade",
         "Points scored per 100 possessions above league average", "05_top_offenses.png"),
        ("def", "The best defenses of the decade",
         "Points allowed per 100 possessions below league average", "06_top_defenses.png"),
    ):
        r["rank_before"] = r[f"{side}_a"].rank(ascending=False, method="min").astype(int)
        r["rank_after"] = r[f"{side}_m"].rank(ascending=False, method="min").astype(int)
        rank_chart(r, f"{side}_a", f"{side}_m", title, xlabel, name)
        top = r[(r.rank_before <= 7) | (r.rank_after <= 7)]
        panels.append((("Offense" if side == "off" else "Defense"),
                       top[["season", "team", "rank_before", "rank_after"]].copy()))
    chart_rank_shuffle(panels)


def chart_best_net(r, n=7, worst=False):
    """Best (or worst) net ratings: each team's change plus its rank before -> after."""
    rank_chart(r, "net_a", "net_m",
               f"The {'worst' if worst else 'best'} teams of the decade",
               "Net rating (point differential per 100 possessions)",
               "14_worst_net_ratings.png" if worst else "09_top_net_ratings.png",
               n=n, worst=worst)


def rank_chart(r, col_a, col_m, title, xlabel, name, n=7, worst=False, ascending=None):
    """Arrows from actual to no-garbage-time value, plus a rank before -> after column.

    worst: the list ranks bad teams (moving up the list is bad, colored orange).
    ascending: rank 1 is the lowest value (defaults to `worst`, as for net rating).
    """
    if ascending is None:
        ascending = worst
    r = r[["season", "team", col_a, col_m]].rename(columns={col_a: "net_a", col_m: "net_m"})
    r["rank_before"] = r.net_a.rank(ascending=ascending, method="min").astype(int)
    r["rank_after"] = r.net_m.rank(ascending=ascending, method="min").astype(int)
    data = r[(r.rank_before <= n) | (r.rank_after <= n)]
    data = data.sort_values(["rank_after", "net_m"], ascending=[True, ascending]).iloc[::-1]

    fig, ax = frame(title, figsize=(11, 6.6 + 0.45 * max(0, len(data) - 8)), left=0.22)
    fig.subplots_adjust(right=0.80, bottom=0.15, top=0.78)
    legend_line(fig, [("●", BEFORE, False), (" Actual    ", INK_2, False),
                      ("●", BLUE, False), (" Garbage time removed", INK_2, False)])
    y = list(range(len(data)))
    lo, hi = min(data.net_a.min(), data.net_m.min()), max(data.net_a.max(), data.net_m.max())
    ax.set_xlim(lo - (0.75 if ascending else 0.35), hi + (0.35 if ascending else 0.55))
    ax.set_ylim(-0.6, len(data) - 0.4)

    change = data.net_m - data.net_a
    biggest = change.idxmin() if ascending else change.idxmax()
    for i, row in enumerate(data.itertuples()):
        if row.Index == biggest:
            ax.axhspan(i - 0.42, i + 0.42, color="#fdeee7" if worst else "#eef4fc",
                       zorder=0)
        head = 0.06 if row.net_m < row.net_a else -0.06
        ax.annotate("", xy=(row.net_m + head, i), xytext=(row.net_a, i),
                    arrowprops=dict(arrowstyle="-|>,head_width=0.25,head_length=0.5",
                                    color=BLUE_LIGHT, linewidth=3, shrinkA=4, shrinkB=0),
                    zorder=1)
        diff = round(row.net_m - row.net_a, 1)
        text = "no change" if diff == 0 else f"{diff:+.1f}".replace("-", "−")
        ink = MUTED if diff == 0 else BLUE
        if ascending:
            ax.text(min(row.net_a, row.net_m) - 0.12, i, text, ha="right",
                    va="center", fontsize=12, fontname=FONT_BOLD, color=ink)
        else:
            ax.text(max(row.net_a, row.net_m) + 0.12, i, text,
                    va="center", fontsize=12, fontname=FONT_BOLD, color=ink)
        # Rank column, outside the plot on the right.
        moved = row.rank_after - row.rank_before
        # Up the list is good on the best chart, bad on the worst chart.
        if moved < 0:
            mark, color = "▲", ORANGE if worst else BLUE
        elif moved > 0:
            mark, color = "▼", BLUE if worst else ORANGE
        else:
            mark, color = "–", MUTED
        ax.text(1.06, i, f"{row.rank_before}", transform=ax.get_yaxis_transform(),
                ha="right", va="center", fontsize=12, color=MUTED)
        ax.text(1.09, i, "→", transform=ax.get_yaxis_transform(),
                ha="center", va="center", fontsize=11, color=MUTED)
        ax.text(1.15, i, f"{row.rank_after}", transform=ax.get_yaxis_transform(),
                ha="right", va="center", fontsize=13, fontname=FONT_BOLD, color=INK)
        ax.text(1.18, i, mark, transform=ax.get_yaxis_transform(),
                ha="left", va="center", fontsize=11, color=color)
    ax.text(1.105, len(data) - 0.25, "WORST" if worst else "RANK", transform=ax.get_yaxis_transform(),
            ha="center", va="bottom", fontsize=9, color=MUTED, fontname=FONT_BOLD)

    ax.scatter(data.net_a, y, s=110, color=BEFORE, zorder=2, edgecolor=SURFACE, linewidth=2)
    ax.scatter(data.net_m, y, s=150, color=BLUE, zorder=3, edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(y, [label(t) for t in data.itertuples()], color=INK, fontsize=12.5)
    ax.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(1))
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:+.0f}".replace("-", "−"))
    ax.set_xlabel(xlabel, labelpad=8)
    ax.spines["bottom"].set_visible(False)
    grid(ax, "x")
    save(fig, name)


def chart_three_ratings(r, n=5):
    """Top n team-seasons for offense, defense and net, actual vs. no garbage time."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 6))
    fig.subplots_adjust(left=0.115, right=0.975, top=0.72, bottom=0.12, wspace=0.62)
    fig.text(0.03, 0.92, "The decade's best teams, with garbage time removed",
             fontsize=21, fontname=FONT_BOLD, color=INK)
    legend_line(fig, [("●", BEFORE, False), (" Actual    ", INK_2, False),
                      ("●", BLUE, False), (" Garbage time removed", INK_2, False)],
                x=0.03)
    fig.text(0.03, 0.035, SOURCE + ". Offense and defense are relative to each "
             "season's league average.", fontsize=9, color=MUTED)
    specs = (("Offense", "off", "Points scored vs. league avg"),
             ("Defense", "def", "Points allowed vs. league avg"),
             ("Net rating", "net", "Point differential"))
    for ax, (heading, side, unit) in zip(axes, specs):
        a, m = f"{side}_a", f"{side}_m"
        top = r.nlargest(n, m).iloc[::-1]
        y = list(range(len(top)))
        for i, (b, v) in enumerate(zip(top[a], top[m])):
            ax.plot([b, v], [i, i], color=BEFORE, linewidth=3, solid_capstyle="round", zorder=1)
            ax.text(max(b, v) + 0.12, i, f"{v - b:+.1f}", va="center", fontsize=11,
                    fontname=FONT_BOLD, color=BLUE)
        ax.scatter(top[a], y, s=90, color=BEFORE, edgecolor=SURFACE, linewidth=2, zorder=2)
        ax.scatter(top[m], y, s=130, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3)
        ax.set_yticks(y, [label(t) for t in top.itertuples()], fontsize=11.5, color=INK)
        lo, hi = min(top[a].min(), top[m].min()), max(top[a].max(), top[m].max())
        ax.set_xlim(lo - 0.4, hi + 0.9)
        ax.set_ylim(-0.6, n - 0.4)
        ax.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(1))
        ax.xaxis.set_major_formatter(lambda v, _: f"{v:+.0f}")
        ax.spines["bottom"].set_visible(False)
        ax.tick_params(length=0, pad=6)
        grid(ax, "x")
        ax.set_title(heading, loc="left", fontsize=15, fontname=FONT_BOLD,
                     color=INK, pad=26, x=-0.55)
        ax.text(-0.55, 1.03, unit, transform=ax.transAxes, fontsize=10, color=MUTED)
    save(fig, "08_best_off_def_net.png")


def official_ratings():
    """NBA.com's published team ratings (cached by main.py --historical)."""
    frames = []
    for path in sorted(glob.glob("data/cache/history/*.csv")):
        d = pd.read_csv(path)
        d["season"] = Path(path).stem
        frames.append(d)
    o = pd.concat(frames)
    o = o[o.season.between("2015-16", "2025-26")].copy()
    weights = o.groupby("season").POSS.transform("sum")
    for col in ("OFF_RATING", "DEF_RATING"):
        o[f"LG_{col}"] = (o[col] * o.POSS).groupby(o.season).transform("sum") / weights
    return o


def table_image(rows, title, subtitle, value_col, value_name, diff_label, name, n=10,
                bar_color=BLUE, highlight="#eef4fc"):
    """A clean ranked table rendered as an image."""
    rows = rows.head(n).reset_index(drop=True)
    fig = plt.figure(figsize=(9, 2.4 + 0.52 * n))
    h = fig.get_figheight()
    top = 1 - 1.55 / h          # header row position (figure fraction)
    step = 0.52 / h
    fig.text(0.06, 1 - 0.55 / h, title, fontsize=21, fontname=FONT_BOLD, color=INK)
    fig.text(0.06, 1 - 0.90 / h, subtitle, fontsize=12, color=INK_2)

    cols = {"rank": 0.06, "team": 0.11, "record": 0.47, "value": 0.62,
            "league": 0.74, "diff": 0.86}
    for key, text, ha in (("team", "TEAM", "left"), ("record", "RECORD", "center"),
                          ("value", value_name, "center"), ("league", "LEAGUE AVG", "center"),
                          ("diff", diff_label, "left")):
        fig.text(cols[key] + (-0.06 if key == "diff" else 0), top, text, fontsize=9,
                 color=MUTED, ha=ha, fontname=FONT_BOLD)
    fig.add_artist(plt.Line2D([0.06, 0.95], [top - 0.38 * step] * 2, color=AXIS,
                              linewidth=1, transform=fig.transFigure))

    max_diff = rows.gap.abs().max()
    for i, row in rows.iterrows():
        y = top - (i + 1) * step
        first = i == 0
        if first:
            fig.add_artist(Rectangle((0.045, y - 0.42 * step), 0.91, 0.84 * step,
                                     color=highlight, transform=fig.transFigure, zorder=0))
        fig.text(cols["rank"], y, f"{i + 1}", fontsize=12, color=MUTED, va="center",
                 fontname=FONT_BOLD)
        fig.text(cols["team"], y, SHORT.get(row.TEAM_NAME, row.TEAM_NAME.split()[-1]),
                 fontsize=13, color=INK, va="center", fontname=FONT_BOLD)
        fig.text(cols["team"] + 0.16, y, row.season, fontsize=11.5, color=INK_2, va="center")
        fig.text(cols["record"], y, f"{row.W}-{row.L}", fontsize=12, color=INK_2,
                 va="center", ha="center")
        fig.text(cols["value"], y, f"{row[value_col]:.1f}", fontsize=13, color=INK,
                 va="center", ha="center", fontname=FONT_BOLD)
        fig.text(cols["league"], y, f"{row.league:.1f}", fontsize=12, color=MUTED,
                 va="center", ha="center")
        bar_w = 0.065 * abs(row.gap) / max_diff
        fig.add_artist(FancyBboxPatch(
            (cols["diff"] - 0.06, y - 0.16 * step), bar_w, 0.32 * step,
            boxstyle="round,pad=0,rounding_size=0.004", mutation_aspect=h / 9 * 0.9,
            color=bar_color, linewidth=0, transform=fig.transFigure))
        fig.text(cols["diff"] - 0.06 + bar_w + 0.01, y, f"{row.gap:+.1f}".replace("-", "−"),
                 fontsize=12, color=INK, va="center", fontname=FONT_BOLD)
        if i < len(rows) - 1:
            fig.add_artist(plt.Line2D([0.06, 0.95], [y - 0.5 * step] * 2, color=GRID,
                                      linewidth=0.8, transform=fig.transFigure))
    fig.text(0.06, 0.25 / h, "Data: NBA.com official team ratings, 2015-16 to 2025-26 "
             "regular seasons", fontsize=9, color=MUTED)
    save(fig, name)


def tables_top_units():
    o = official_ratings()
    off = o.assign(gap=o.OFF_RATING - o.LG_OFF_RATING, league=o.LG_OFF_RATING)
    table_image(off.sort_values("gap", ascending=False),
                "The best offenses of the decade",
                "Ranked by how far each team was above its season's league average",
                "OFF_RATING", "OFF RTG", "VS. AVG", "10_table_top_offenses.png")
    de = o.assign(gap=o.DEF_RATING - o.LG_DEF_RATING, league=o.LG_DEF_RATING)
    table_image(de.sort_values("gap"),
                "The best defenses of the decade",
                "Ranked by how far each team was below its season's league average",
                "DEF_RATING", "DEF RTG", "VS. AVG", "11_table_top_defenses.png")


def worst_defenses(ratings, n=10):
    """Worst defenses vs. league average: official table + before/after chart."""
    o = official_ratings()
    o["gap"] = o.DEF_RATING - o.LG_DEF_RATING
    o["league"] = o.LG_DEF_RATING
    table_image(o.sort_values("gap", ascending=False),
                "The worst defenses of the decade",
                "Ranked by how far each team was above its season's league average",
                "DEF_RATING", "DEF RTG", "VS. AVG", "12_table_worst_defenses.png",
                n=n, bar_color=ORANGE, highlight="#fdeee7")

    # After = official rating + our play-by-play change, against a league
    # average shifted by the same play-by-play change, so it matches the table.
    r = ratings.copy()
    lg_a = r.groupby("season").apply(
        lambda x: 100 * x.actual_pts.sum() / x.actual_poss.sum(), include_groups=False)
    lg_m = r.groupby("season").apply(
        lambda x: 100 * x.mercy_pts.sum() / x.mercy_poss.sum(), include_groups=False)
    r = r.merge(o[["season", "TEAM_NAME", "DEF_RATING", "LG_DEF_RATING"]],
                left_on=["season", "team"], right_on=["season", "TEAM_NAME"], how="left")
    if r.DEF_RATING.isna().any():
        raise ValueError("Team names did not match the official ratings")
    r["bad_a"] = r.DEF_RATING - r.LG_DEF_RATING
    r["bad_m"] = (r.DEF_RATING + r.mercy_drtg - r.actual_drtg) - (
        r.LG_DEF_RATING + r.season.map(lg_m) - r.season.map(lg_a))
    r["rank_before"] = r.bad_a.rank(ascending=False, method="min").astype(int)
    r["rank_after"] = r.bad_m.rank(ascending=False, method="min").astype(int)
    rank_chart(r, "bad_a", "bad_m", "The worst defenses of the decade",
               "Points allowed per 100 possessions above league average",
               "13_worst_defenses.png", n=n, worst=True, ascending=False)


def chart_rank_shuffle(panels):
    """Slope chart: top-7 ranks with and without garbage time."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 6.2))
    fig.subplots_adjust(left=0.04, right=0.96, top=0.70, bottom=0.10, wspace=0.25)
    fig.text(0.04, 0.92, "Same teams at the top, just a little better",
             fontsize=21, fontname=FONT_BOLD, color=INK)
    fig.text(0.04, 0.865, "Top 7 offenses and defenses of 2015-16 to 2025-26, ranked "
             "against their season's league average", fontsize=12.5, color=INK_2)
    fig.text(0.04, 0.035, SOURCE, fontsize=9, color=MUTED)
    for ax, (heading, top) in zip(axes, panels):
        ax.set_xlim(-1.25, 2.25)
        ax.set_ylim(7.6, 0.2)
        ax.axis("off")
        ax.text(0.5, 1.13, heading, ha="center", fontsize=15,
                fontname=FONT_BOLD, color=INK, transform=ax.get_xaxis_transform())
        for x, text in ((0, "Actual"), (1, "No garbage time")):
            ax.text(x, 1.04, text, ha="center", va="center", fontsize=10.5,
                    color=MUTED, transform=ax.get_xaxis_transform())
        for row in top.itertuples():
            moved = row.rank_before != row.rank_after
            color = BLUE if moved else BEFORE
            b, a = min(row.rank_before, 8), min(row.rank_after, 8)
            ax.plot([0, 1], [b, a], color=color, linewidth=3 if moved else 2,
                    solid_capstyle="round", zorder=2 if moved else 1)
            ax.scatter([0, 1], [b, a], s=60, color=color, zorder=3,
                       edgecolor=SURFACE, linewidth=1.5)
            name = label(row)
            weight = FONT_BOLD if moved else FONT
            ink = INK if moved else INK_2
            if row.rank_before <= 7:
                ax.text(-0.1, b, f"{name}  {row.rank_before}", ha="right", va="center",
                        fontsize=11, fontname=weight, color=ink)
            if row.rank_after <= 7:
                ax.text(1.1, a, f"{row.rank_after}  {name}", ha="left", va="center",
                        fontsize=11, fontname=weight, color=ink)
    save(fig, "07_top7_rank_changes.png")


def main():
    CHARTS.mkdir(parents=True, exist_ok=True)
    scen = pd.read_csv(OUT / "scenario_comparison.csv")
    games = pd.read_csv(OUT / "all_games.csv", dtype={"game_id": str})
    ratings = pd.read_csv(OUT / "all_team_ratings.csv")

    chart_games_cut(scen)
    chart_blowouts(blowout_shares())
    chart_no_comebacks(games)
    chart_net_changes(ratings)
    chart_top_units(ratings)
    tables_top_units()
    worst_defenses(ratings)


if __name__ == "__main__":
    main()
