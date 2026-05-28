"""
Shared visual theme constants for the NBA xShot + RAPM dashboard.

Import from here instead of hard-coding colours and layout dicts in every page.
All chart-builder functions in viz.py and court.py use these values so that
a single change here propagates everywhere.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

ACCENT       = "#E8462A"          # primary red-orange (RAPM, main action)
ACCENT_BLUE  = "#4C9BE8"          # xRAPM, secondary metric
ACCENT_GREEN = "#2ECC71"          # positive / above expected
ACCENT_RED   = "#E74C3C"          # negative / below expected
ACCENT_GOLD  = "#F4D03F"          # shot difficulty / tertiary highlight
MUTED        = "rgba(160,165,175,0.75)"
MUTED_LIGHT  = "rgba(200,205,215,0.55)"
GRID         = "rgba(80,80,80,0.25)"
ZERO_LINE    = "rgba(200,200,200,0.40)"
SURFACE      = "rgba(255,255,255,0.04)"
SURFACE_MED  = "rgba(255,255,255,0.07)"
BORDER       = "rgba(255,255,255,0.09)"

# Tier colours for percentile bars
TIER_ELITE    = "#1A9E4E"   # ≥ 90th
TIER_GREAT    = "#2ECC71"   # 75–89th
TIER_ABOVE    = "#A4C429"   # 60–74th
TIER_AVG      = "#C8A82A"   # 40–59th
TIER_BELOW    = "#E67E22"   # 25–39th
TIER_POOR     = "#E74C3C"   # < 25th

TIER_LEGEND = (
    f"<span style='color:{TIER_ELITE}'>■</span> Elite (≥90th)  "
    f"<span style='color:{TIER_GREAT}'>■</span> Great (75–89th)  "
    f"<span style='color:{TIER_ABOVE}'>■</span> Above avg (60–74th)  "
    f"<span style='color:{TIER_AVG}'>■</span> Average (40–59th)  "
    f"<span style='color:{TIER_BELOW}'>■</span> Below avg (25–39th)  "
    f"<span style='color:{TIER_POOR}'>■</span> Poor (&lt;25th)"
)

def tier_color(percentile: float) -> str:
    """Map a percentile (0–100) to a tier hex colour."""
    if percentile >= 90: return TIER_ELITE
    if percentile >= 75: return TIER_GREAT
    if percentile >= 60: return TIER_ABOVE
    if percentile >= 40: return TIER_AVG
    if percentile >= 25: return TIER_BELOW
    return TIER_POOR


# ---------------------------------------------------------------------------
# Base chart layout
# ---------------------------------------------------------------------------

_BASE = dict(
    plot_bgcolor  = "rgba(0,0,0,0)",
    paper_bgcolor = "rgba(0,0,0,0)",
    font          = dict(color="rgba(220,225,232,0.9)", size=12),
    hoverlabel    = dict(bgcolor="rgba(20,22,30,0.92)", font_size=12,
                         font_color="rgba(220,225,232,0.95)"),
    legend        = dict(orientation="h", y=1.08, font=dict(size=11)),
    hovermode     = "x unified",
    margin        = dict(l=20, r=20, t=50, b=20),
)

_XAXIS_BASE = dict(
    showgrid        = True,
    gridcolor       = GRID,
    zeroline        = False,
    linecolor       = "rgba(255,255,255,0.08)",
    tickcolor       = "rgba(255,255,255,0.15)",
)
_YAXIS_BASE = dict(**_XAXIS_BASE)


def chart_layout(
    height: int = 380,
    hovermode: str = "x unified",
    legend_y: float = 1.08,
    margin: dict | None = None,
    **overrides,
) -> dict:
    """
    Return a Plotly layout dict pre-configured for the dark dashboard theme.

    All keys are safe to pass here — they will NOT be passed again as kwargs
    to update_layout, avoiding 'multiple values for keyword argument' errors.

    Parameters
    ----------
    height    : chart height in pixels
    hovermode : Plotly hovermode string
    legend_y  : vertical position of the legend (0–1.2)
    margin    : dict(l, r, t, b) override; defaults to _BASE margin
    **overrides : any additional layout keys (xaxis_title, barmode, etc.)
    """
    layout = {**_BASE, "height": height, "hovermode": hovermode}
    layout["legend"] = {**_BASE["legend"], "y": legend_y}
    if margin is not None:
        layout["margin"] = margin
    layout.update(overrides)
    return layout


def axis(title: str = "", **overrides) -> dict:
    """Return a styled axis config dict."""
    base = dict(title=title, **_XAXIS_BASE)
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Modebar config (used in every st.plotly_chart call)
# ---------------------------------------------------------------------------

MODEBAR = {"modeBarButtonsToAdd": ["downloadImage"], "displaylogo": False}


# ---------------------------------------------------------------------------
# Section label HTML helper
# ---------------------------------------------------------------------------

def section_label(text: str) -> str:
    """Return an HTML string for a small-caps section divider label."""
    return (
        f'<div style="font-size:0.70rem;font-weight:700;letter-spacing:0.13em;'
        f'color:rgba(180,180,180,0.50);text-transform:uppercase;margin:28px 0 10px 0">'
        f'{text}</div>'
    )


# ---------------------------------------------------------------------------
# Metric card HTML helpers
# ---------------------------------------------------------------------------

def metric_card(
    label: str,
    value: str,
    sub: str = "",
    accent: str = ACCENT,
    img_url: str = "",
    img_round: bool = False,
) -> str:
    """
    Return an HTML string for a single metric card (left-border style).
    Wrap multiple cards in a flex container via metric_row().
    """
    img_html = ""
    if img_url:
        shape = "border-radius:50%;" if img_round else "border-radius:4px;"
        img_html = (
            f'<div style="margin-bottom:6px">'
            f'<img src="{img_url}" style="height:34px;width:auto;max-width:60px;'
            f'object-fit:contain;{shape}" onerror="this.style.display=\'none\'">'
            f'</div>'
        )
    sub_html = f'<div style="font-size:0.72rem;color:{MUTED};margin-top:3px">{sub}</div>' if sub else ""
    return (
        f'<div style="flex:1;min-width:140px;background:{SURFACE};'
        f'border-left:3px solid {accent};border-radius:8px;padding:12px 14px">'
        f'{img_html}'
        f'<div style="font-size:0.68rem;font-weight:600;color:{MUTED_LIGHT};'
        f'text-transform:uppercase;letter-spacing:0.05em;white-space:nowrap">{label}</div>'
        f'<div style="font-size:1.45rem;font-weight:700;margin-top:4px">{value}</div>'
        f'{sub_html}</div>'
    )


def metric_row(*cards: str) -> str:
    """Wrap metric card HTML strings in a flex row."""
    return f'<div style="display:flex;gap:10px;flex-wrap:wrap">{"".join(cards)}</div>'


def insight_card(icon: str, headline: str, body: str, accent: str = ACCENT) -> str:
    """Return an HTML string for a 'key finding' insight card."""
    return (
        f'<div style="flex:1;min-width:220px;background:{SURFACE_MED};'
        f'border:1px solid {BORDER};border-top:2px solid {accent};'
        f'border-radius:10px;padding:16px 18px">'
        f'<div style="font-size:1.4rem;margin-bottom:8px">{icon}</div>'
        f'<div style="font-size:0.88rem;font-weight:700;color:rgba(220,225,232,0.95);'
        f'margin-bottom:6px">{headline}</div>'
        f'<div style="font-size:0.78rem;color:{MUTED};line-height:1.5">{body}</div>'
        f'</div>'
    )


def nav_tile(icon: str, title: str, desc: str) -> str:
    """Return an HTML string for a navigation tile."""
    return (
        f'<div style="flex:1;min-width:160px;background:{SURFACE};'
        f'border:1px solid {BORDER};border-radius:10px;padding:18px 16px">'
        f'<div style="font-size:1.9rem;margin-bottom:8px">{icon}</div>'
        f'<div style="font-size:0.95rem;font-weight:700;color:#F0F2F5;margin-bottom:4px">{title}</div>'
        f'<div style="font-size:0.74rem;color:{MUTED};line-height:1.4">{desc}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Article-format helpers
# ---------------------------------------------------------------------------

# Shared CSS injected once at the top of any article-format page
ARTICLE_CSS = f"""
<style>
.art-section {{
    border-left: 3px solid {ACCENT};
    padding: 2px 0 2px 14px;
    margin: 2.8rem 0 0.6rem 0;
}}
.art-section .art-num {{
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: {MUTED};
    margin-bottom: 2px;
}}
.art-section .art-title {{
    font-size: 1.45rem;
    font-weight: 700;
    color: rgba(220,225,232,0.96);
    line-height: 1.2;
}}
.art-divider {{
    border: none;
    border-top: 1px solid rgba(255,255,255,0.07);
    margin: 2rem 0;
}}
.finding-box {{
    background: rgba(232,70,42,0.08);
    border-left: 3px solid {ACCENT};
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
    margin: 14px 0;
    font-size: 0.92rem;
    font-weight: 600;
    color: rgba(220,225,232,0.92);
    line-height: 1.5;
}}
.finding-box.blue {{
    background: rgba(76,155,232,0.08);
    border-left-color: {ACCENT_BLUE};
}}
.finding-box.green {{
    background: rgba(46,204,113,0.08);
    border-left-color: {ACCENT_GREEN};
}}
.chart-caption {{
    font-size: 0.75rem;
    color: {MUTED};
    font-style: italic;
    margin-top: 4px;
    line-height: 1.45;
}}
.interactive-well {{
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 12px;
    padding: 20px 22px 16px 22px;
    margin: 0.5rem 0 1.5rem 0;
}}
.interactive-well .well-label {{
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: {ACCENT_GOLD};
    margin-bottom: 10px;
}}
</style>
"""


def art_section(number: str, title: str) -> str:
    """HTML for an article-section heading (number + title with left accent bar)."""
    return (
        f'<div class="art-section">'
        f'<div class="art-num">{number}</div>'
        f'<div class="art-title">{title}</div>'
        f'</div>'
    )


def finding(text: str, variant: str = "") -> str:
    """
    HTML for a key-finding callout box.
    variant: "" (red), "blue", or "green"
    """
    cls = f"finding-box {variant}".strip()
    return f'<div class="{cls}">{text}</div>'


def chart_caption(text: str) -> str:
    """HTML for a below-chart interpretive caption."""
    return f'<div class="chart-caption">↑ {text}</div>'


def interactive_well_open() -> str:
    """Opening tag for an interactive section well."""
    return (
        '<div class="interactive-well">'
        '<div class="well-label">🎛 Interactive — try it yourself</div>'
    )


def interactive_well_close() -> str:
    return '</div>'
