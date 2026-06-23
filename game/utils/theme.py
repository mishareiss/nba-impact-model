"""
Shared visual theme constants for the NBA Impact Dashboard.

Import from here instead of hard-coding colours and layout dicts in every page.
All chart-builder functions in viz.py and court.py use these values so that
a single change here propagates everywhere.

Color system aligned with DESIGN_PROPOSAL.md target spec.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Core colour palette  (target spec)
# ---------------------------------------------------------------------------

BG             = "#09090B"          # page background
SURFACE        = "#18181B"          # card / section backgrounds
SURFACE_MED    = "#1F1F23"          # interactive hover state
SURFACE_HOVER  = "#1F1F23"
BORDER         = "#27272A"          # all borders and dividers
BORDER_SUBTLE  = "rgba(255,255,255,0.06)"

TEXT_PRIMARY   = "#FAFAFA"          # main headings, metric values
TEXT_SECONDARY = "#A1A1AA"          # supporting text, captions
TEXT_MUTED     = "#71717A"          # de-emphasised labels, timestamps (4.4:1 contrast on BG)

# Accent colours
ACCENT         = "#60A5FA"          # primary blue — xRAPM, links, interactive
ACCENT_HOVER   = "#93C5FD"
ACCENT_BLUE    = "#818CF8"          # indigo — secondary blue for charts
ACCENT_GREEN   = "#22C55E"          # positive / above expected
ACCENT_RED     = "#EF4444"          # negative / below expected
ACCENT_GOLD    = "#F59E0B"          # warning / shot difficulty
ACCENT_PURPLE  = "#A78BFA"          # defensive metrics (D-RAPM)

# Semantic aliases (used in components and pages)
POSITIVE = ACCENT_GREEN
WARNING  = ACCENT_GOLD
NEGATIVE = ACCENT_RED

# Chart helpers
MUTED       = TEXT_SECONDARY
MUTED_LIGHT = TEXT_MUTED
GRID        = "rgba(255,255,255,0.06)"
ZERO_LINE   = "rgba(200,200,200,0.30)"

# ---------------------------------------------------------------------------
# Tier colours for percentile bars  (Baseball Savant style)
# ---------------------------------------------------------------------------

TIER_ELITE = "#1A9E4E"   # ≥ 90th
TIER_GREAT = "#22C55E"   # 75–89th
TIER_ABOVE = "#84CC16"   # 60–74th
TIER_AVG   = "#EAB308"   # 40–59th
TIER_BELOW = "#F97316"   # 25–39th
TIER_POOR  = "#EF4444"   # < 25th

TIER_LEGEND = (
    f"<span style='color:{TIER_ELITE}'>■</span> Elite (≥90th)&nbsp;&nbsp;"
    f"<span style='color:{TIER_GREAT}'>■</span> Great (75–89th)&nbsp;&nbsp;"
    f"<span style='color:{TIER_ABOVE}'>■</span> Above avg (60–74th)&nbsp;&nbsp;"
    f"<span style='color:{TIER_AVG}'>■</span> Average (40–59th)&nbsp;&nbsp;"
    f"<span style='color:{TIER_BELOW}'>■</span> Below avg (25–39th)&nbsp;&nbsp;"
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
    font          = dict(color=TEXT_SECONDARY, size=12),
    hoverlabel    = dict(
        bgcolor    = "#111114",
        font_size  = 12,
        font_color = TEXT_PRIMARY,
        bordercolor = BORDER,
    ),
    legend   = dict(orientation="h", y=1.08, font=dict(size=11)),
    hovermode = "x unified",
    margin    = dict(l=20, r=20, t=50, b=20),
)

_XAXIS_BASE = dict(
    showgrid   = True,
    gridcolor  = GRID,
    zeroline   = False,
    linecolor  = BORDER,
    tickcolor  = BORDER,
    tickfont   = dict(color=TEXT_SECONDARY, size=11),
)
_YAXIS_BASE = dict(**_XAXIS_BASE)


def chart_layout(
    height: int = 380,
    hovermode: str = "x unified",
    legend_y: float = 1.08,
    margin: dict | None = None,
    **overrides,
) -> dict:
    layout = {**_BASE, "height": height, "hovermode": hovermode}
    layout["legend"] = {**_BASE["legend"], "y": legend_y}
    if margin is not None:
        layout["margin"] = margin
    layout.update(overrides)
    return layout


def axis(title: str = "", **overrides) -> dict:
    base = dict(title=title, **_XAXIS_BASE)
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Modebar config (used in every st.plotly_chart call)
# ---------------------------------------------------------------------------

MODEBAR = {"modeBarButtonsToAdd": ["downloadImage"], "displaylogo": False}


# ---------------------------------------------------------------------------
# Global CSS  (inject once per page via inject_global_css())
# ---------------------------------------------------------------------------

GLOBAL_CSS = f"""
<style>
/* ── Core background & base text ─────────────────────────────────── */
.stApp {{
    background-color: {BG};
    color: {TEXT_PRIMARY};
}}
/* Make sure all markdown text is visible */
.stApp p, .stApp li, .stApp span {{
    color: inherit;
}}
.stMarkdown, .stMarkdown p, .stMarkdown li {{
    color: {TEXT_SECONDARY};
    line-height: 1.65;
}}
/* Headings stay bright */
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
.stMarkdown h4, .stMarkdown h5 {{
    color: {TEXT_PRIMARY} !important;
}}

/* ── Sidebar ─────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
    background-color: #111113;
    border-right: 1px solid {BORDER};
}}
[data-testid="stSidebar"] .stMarkdown p {{
    color: {TEXT_SECONDARY};
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin: 18px 0 4px 0;
}}
[data-testid="stSidebarNavLink"] {{
    border-radius: 6px;
    padding: 6px 10px;
    color: {TEXT_SECONDARY} !important;
    font-size: 0.875rem;
    font-weight: 500;
    transition: background 0.15s;
}}
[data-testid="stSidebarNavLink"]:hover {{
    background: rgba(96, 165, 250, 0.08);
    color: {TEXT_PRIMARY} !important;
}}
[data-testid="stSidebarNavLink"][aria-current="page"] {{
    background: rgba(96, 165, 250, 0.10);
    border-left: 3px solid {ACCENT};
    color: {TEXT_PRIMARY} !important;
    font-weight: 600;
    padding-left: 7px;
}}

/* ── Tabs ────────────────────────────────────────────────────────── */
[data-baseweb="tab-list"] {{
    gap: 2px;
    background: transparent;
    border-bottom: 1px solid {BORDER};
}}
[data-baseweb="tab"] {{
    background: transparent !important;
    border: none !important;
    color: {TEXT_SECONDARY} !important;
    font-size: 0.85rem;
    font-weight: 500;
    padding: 8px 16px !important;
    border-radius: 4px 4px 0 0;
}}
[data-baseweb="tab"]:hover {{
    color: {TEXT_PRIMARY} !important;
    background: rgba(255,255,255,0.04) !important;
}}
[aria-selected="true"][data-baseweb="tab"] {{
    color: {TEXT_PRIMARY} !important;
    border-bottom: 2px solid {ACCENT} !important;
    font-weight: 600;
}}
[data-baseweb="tab-panel"] {{
    padding-top: 20px;
}}

/* ── Expanders ───────────────────────────────────────────────────── */
[data-testid="stExpander"] {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    background: {SURFACE};
    overflow: hidden;
}}
[data-testid="stExpander"] summary {{
    font-size: 0.875rem;
    font-weight: 600;
    color: {TEXT_SECONDARY};
    padding: 12px 16px;
}}
[data-testid="stExpander"] summary:hover {{
    color: {TEXT_PRIMARY};
}}
[data-testid="stExpander"] .stMarkdown p {{
    color: {TEXT_SECONDARY};
}}

/* ── Metrics ─────────────────────────────────────────────────────── */
[data-testid="stMetricLabel"] {{
    font-size: 0.65rem !important;
    font-weight: 700 !important;
    color: {TEXT_SECONDARY} !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}}
[data-testid="stMetricValue"] {{
    font-size: 1.45rem !important;
    color: {TEXT_PRIMARY} !important;
}}
[data-testid="stMetricDelta"] {{
    font-size: 0.78rem !important;
}}

/* ── Dataframe / tables ──────────────────────────────────────────── */
[data-testid="stDataFrame"] {{
    font-size: 0.80rem;
}}
[data-testid="stDataFrame"] th {{
    background: {SURFACE} !important;
    color: {TEXT_SECONDARY} !important;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid {BORDER} !important;
}}
[data-testid="stDataFrame"] td {{
    color: {TEXT_PRIMARY} !important;
    border-bottom: 1px solid {BORDER_SUBTLE} !important;
}}

/* ── Inputs / selects ────────────────────────────────────────────── */
[data-baseweb="select"] div {{
    background: {SURFACE} !important;
    border-color: {BORDER} !important;
    color: {TEXT_PRIMARY} !important;
}}
[data-baseweb="select"] svg {{
    color: {TEXT_SECONDARY} !important;
}}
[data-baseweb="menu"] {{
    background: #1C1C1F !important;
    border: 1px solid {BORDER} !important;
}}
[data-baseweb="menu"] li {{
    color: {TEXT_SECONDARY} !important;
}}
[data-baseweb="menu"] li:hover {{
    background: {SURFACE_MED} !important;
    color: {TEXT_PRIMARY} !important;
}}
[data-baseweb="input"] {{
    background: {SURFACE} !important;
    border-color: {BORDER} !important;
}}
[data-baseweb="input"] input {{
    color: {TEXT_PRIMARY} !important;
}}
[data-testid="stNumberInput"] input {{
    background: {SURFACE} !important;
    border-color: {BORDER} !important;
    color: {TEXT_PRIMARY} !important;
}}
[data-testid="stMultiSelect"] {{
    background: {SURFACE} !important;
}}
/* ── MultiSelect tag fix ─────────────────────────────────────────────────────
   Root cause (Streamlit 1.55+): baseweb renders the typing InputContainer with
   position:absolute (when unfocused) and width:fit-content, landing it at
   coordinate (0,0) over the first tag chip with a dark background.
   Fix: make the InputContainer and its input transparent.              ── */
/* The absolutely-positioned InputContainer div (style contains "fit-content") */
[data-testid="stMultiSelect"] [data-baseweb="select"] div[style*="fit-content"] {{
    background: transparent !important;
    background-color: transparent !important;
}}
/* The input element itself */
[data-testid="stMultiSelect"] input {{
    background: transparent !important;
    background-color: transparent !important;
    color: {TEXT_PRIMARY} !important;
}}
/* Tag chip outer shell */
[data-testid="stMultiSelect"] [data-baseweb="tag"] {{
    background: rgba(96, 165, 250, 0.15) !important;
    border: 1px solid rgba(96, 165, 250, 0.30) !important;
    color: {ACCENT} !important;
    border-radius: 4px !important;
}}
/* All tag children — catch baseweb's nested div/span/button wrappers */
[data-testid="stMultiSelect"] [data-baseweb="tag"] *,
[data-testid="stMultiSelect"] [data-baseweb="tag"] *::before,
[data-testid="stMultiSelect"] [data-baseweb="tag"] *::after {{
    background: transparent !important;
    background-color: transparent !important;
    color: {ACCENT} !important;
}}
/* Select placeholder text */
[data-baseweb="select"] [data-testid="stWidgetLabel"],
[data-baseweb="select"] input::placeholder {{
    color: {TEXT_MUTED} !important;
}}

/* ── Form elements — labels above inputs ─────────────────────────── */
[data-testid="stWidgetLabel"] {{
    color: {TEXT_SECONDARY} !important;
    font-size: 0.875rem !important;
}}
[data-testid="stWidgetLabel"] p {{
    color: {TEXT_SECONDARY} !important;
}}

/* ── Buttons ─────────────────────────────────────────────────────── */
[data-testid="stBaseButton-secondary"] {{
    background: {SURFACE} !important;
    border-color: {BORDER} !important;
    color: {TEXT_PRIMARY} !important;
    font-size: 0.85rem;
}}
[data-testid="stBaseButton-secondary"]:hover {{
    background: {SURFACE_MED} !important;
    border-color: {ACCENT} !important;
}}
[data-testid="stBaseButton-primary"] {{
    color: #0A0A0D !important;
    font-weight: 600;
}}
/* Form submit buttons */
[data-testid="stFormSubmitButton"] button {{
    font-weight: 600;
}}

/* ── Page links (nav cards) ──────────────────────────────────────── */
.stPageLink a {{
    display: block;
    background: {SURFACE} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 8px;
    padding: 16px;
    color: {TEXT_PRIMARY} !important;
    text-decoration: none;
    transition: border-color 0.15s, background 0.15s;
    font-weight: 600;
    font-size: 0.9rem;
}}
.stPageLink a:hover {{
    background: {SURFACE_MED} !important;
    border-color: {ACCENT} !important;
    color: {TEXT_PRIMARY} !important;
}}

/* ── Captions — need to be readable ─────────────────────────────── */
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {{
    color: {TEXT_SECONDARY} !important;
    font-size: 0.78rem !important;
    line-height: 1.5 !important;
}}

/* ── Dividers ────────────────────────────────────────────────────── */
hr {{
    border-color: {BORDER} !important;
    margin: 1.5rem 0;
}}

/* ── Spinners ────────────────────────────────────────────────────── */
[data-testid="stSpinner"] {{
    color: {ACCENT} !important;
}}

/* ── Radio buttons ───────────────────────────────────────────────── */
[data-testid="stRadio"] label {{
    color: {TEXT_SECONDARY} !important;
    font-size: 0.85rem;
}}
[data-testid="stRadio"] [aria-checked="true"] + div {{
    color: {TEXT_PRIMARY} !important;
}}
/* Radio group label */
[data-testid="stRadio"] > label {{
    color: {TEXT_SECONDARY} !important;
}}

/* ── Select slider ───────────────────────────────────────────────── */
[data-testid="stSlider"] .st-emotion-cache-1uw6e3c p {{
    color: {TEXT_SECONDARY} !important;
}}

/* ── Info / warning / error boxes ───────────────────────────────── */
[data-testid="stAlert"] {{
    background: {SURFACE} !important;
    border-color: {BORDER} !important;
}}
[data-testid="stAlert"] p {{
    color: {TEXT_PRIMARY} !important;
}}

/* ── Number input label ──────────────────────────────────────────── */
[data-testid="stNumberInput"] label {{
    color: {TEXT_SECONDARY} !important;
}}

/* ── Multiselect label ───────────────────────────────────────────── */
[data-testid="stMultiSelect"] label {{
    color: {TEXT_SECONDARY} !important;
}}

/* ── Dialog / modal ──────────────────────────────────────────────── */
[data-testid="stModal"] {{
    background: #18181B !important;
}}
[data-testid="stModal"] p {{
    color: {TEXT_SECONDARY} !important;
}}
[data-testid="stModal"] h1,
[data-testid="stModal"] h2,
[data-testid="stModal"] h3 {{
    color: {TEXT_PRIMARY} !important;
}}

/* ── Article-format components ───────────────────────────────────── */
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
    color: {TEXT_SECONDARY};
    margin-bottom: 2px;
}}
.art-section .art-title {{
    font-size: 1.35rem;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    line-height: 1.2;
}}
.art-divider {{
    border: none;
    border-top: 1px solid {BORDER};
    margin: 2rem 0;
}}
.finding-box {{
    background: rgba(96, 165, 250, 0.07);
    border-left: 3px solid {ACCENT};
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
    margin: 14px 0;
    font-size: 0.88rem;
    font-weight: 500;
    color: {TEXT_PRIMARY};
    line-height: 1.5;
}}
.finding-box.blue {{
    background: rgba(129, 140, 248, 0.07);
    border-left-color: {ACCENT_BLUE};
}}
.finding-box.green {{
    background: rgba(34, 197, 94, 0.07);
    border-left-color: {ACCENT_GREEN};
}}
.finding-box.gold {{
    background: rgba(245, 158, 11, 0.07);
    border-left-color: {ACCENT_GOLD};
}}
.chart-caption {{
    font-size: 0.75rem;
    color: {TEXT_SECONDARY};
    font-style: italic;
    margin-top: 6px;
    line-height: 1.5;
}}
.interactive-well {{
    background: rgba(255,255,255,0.02);
    border: 1px solid {BORDER};
    border-radius: 10px;
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

/* ── Utility ─────────────────────────────────────────────────────── */
.nb-badge {{
    display: inline-block;
    background: rgba(255,255,255,0.06);
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 9px;
    font-size: 0.72rem;
    font-weight: 600;
    color: {TEXT_SECONDARY};
    margin: 2px 3px 2px 0;
    letter-spacing: 0.03em;
}}
.nb-label {{
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.13em;
    color: {TEXT_SECONDARY};
    text-transform: uppercase;
    margin: 24px 0 8px 0;
    display: block;
}}
.nb-divider {{
    border: none;
    border-top: 1px solid {BORDER};
    margin: 1.5rem 0;
}}
</style>
"""

# Keep ARTICLE_CSS as alias for backward compatibility (now same as GLOBAL_CSS)
ARTICLE_CSS = GLOBAL_CSS


def inject_global_css() -> None:
    """Call once per page after st.set_page_config() to apply the full design system."""
    import streamlit as st
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# HTML helper: section label
# ---------------------------------------------------------------------------

def section_label(text: str) -> str:
    return (
        f'<div class="nb-label" style="color:{TEXT_SECONDARY}">{text}</div>'
    )


# ---------------------------------------------------------------------------
# HTML helper: page header
# ---------------------------------------------------------------------------

def page_header(title: str, subtitle: str = "", icon: str = "") -> str:
    icon_html = f'<span style="margin-right:10px">{icon}</span>' if icon else ""
    sub_html = (
        f'<p style="font-size:0.92rem;color:{TEXT_SECONDARY};'
        f'max-width:780px;line-height:1.65;margin:6px 0 0 0">{subtitle}</p>'
    ) if subtitle else ""
    return (
        f'<h1 style="margin-bottom:2px;font-size:1.95rem;font-weight:700;'
        f'color:{TEXT_PRIMARY};letter-spacing:-0.01em">{icon_html}{title}</h1>'
        f'{sub_html}'
    )


# ---------------------------------------------------------------------------
# HTML helpers: metric cards
# ---------------------------------------------------------------------------

def metric_card(
    label: str,
    value: str,
    sub: str = "",
    accent: str = ACCENT,
    img_url: str = "",
    img_round: bool = False,
    trend: str = "",          # "+1.2" or "-0.5" — shows small delta
) -> str:
    img_html = ""
    if img_url:
        shape = "border-radius:50%;" if img_round else "border-radius:4px;"
        img_html = (
            f'<div style="margin-bottom:6px">'
            f'<img src="{img_url}" style="height:34px;width:auto;max-width:60px;'
            f'object-fit:contain;{shape}" onerror="this.style.display=\'none\'">'
            f'</div>'
        )
    sub_html = (
        f'<div style="font-size:0.72rem;color:{TEXT_MUTED};margin-top:3px">{sub}</div>'
    ) if sub else ""
    trend_html = ""
    if trend:
        try:
            v = float(trend)
            col = ACCENT_GREEN if v >= 0 else ACCENT_RED
            sym = "▲" if v >= 0 else "▼"
            trend_html = (
                f'<span style="font-size:0.72rem;color:{col};margin-left:6px;'
                f'font-weight:600">{sym} {abs(v):.1f}</span>'
            )
        except ValueError:
            pass
    return (
        f'<div style="flex:1;min-width:140px;background:{SURFACE};'
        f'border:1px solid {BORDER};border-left:3px solid {accent};'
        f'border-radius:8px;padding:12px 14px">'
        f'{img_html}'
        f'<div style="font-size:0.65rem;font-weight:700;color:{TEXT_SECONDARY};'
        f'text-transform:uppercase;letter-spacing:0.06em;white-space:nowrap">{label}</div>'
        f'<div style="font-size:1.45rem;font-weight:700;margin-top:4px;color:{TEXT_PRIMARY}">'
        f'{value}{trend_html}</div>'
        f'{sub_html}</div>'
    )
# TEXT_MUTED (#71717A) is used for sub labels — intentionally de-emphasised but still legible


def metric_row(*cards: str) -> str:
    return f'<div style="display:flex;gap:10px;flex-wrap:wrap">{"".join(cards)}</div>'


# ---------------------------------------------------------------------------
# HTML helpers: insight and nav cards
# ---------------------------------------------------------------------------

def insight_card(icon: str, headline: str, body: str, accent: str = ACCENT) -> str:
    return (
        f'<div style="flex:1;min-width:220px;background:{SURFACE};'
        f'border:1px solid {BORDER};border-top:2px solid {accent};'
        f'border-radius:8px;padding:16px 18px">'
        f'<div style="font-size:1.3rem;margin-bottom:8px">{icon}</div>'
        f'<div style="font-size:0.875rem;font-weight:700;color:{TEXT_PRIMARY};'
        f'margin-bottom:6px">{headline}</div>'
        f'<div style="font-size:0.78rem;color:{TEXT_SECONDARY};line-height:1.5">{body}</div>'
        f'</div>'
    )


def nav_tile(icon: str, title: str, desc: str, accent: str = ACCENT) -> str:
    return (
        f'<div style="flex:1;min-width:160px;background:{SURFACE};'
        f'border:1px solid {BORDER};border-radius:8px;padding:18px 16px;'
        f'transition:border-color 0.15s">'
        f'<div style="font-size:1.6rem;margin-bottom:10px">{icon}</div>'
        f'<div style="font-size:0.9rem;font-weight:700;color:{TEXT_PRIMARY};'
        f'margin-bottom:4px">{title}</div>'
        f'<div style="font-size:0.75rem;color:{TEXT_SECONDARY};line-height:1.4">{desc}</div>'
        f'</div>'
    )


def player_card_html(
    name: str, team: str, rank: int,
    metric_label: str, metric_value: str,
    percentile: str = "", team_color: str = BORDER,
    sub: str = "",
) -> str:
    pct_html = (
        f'<span style="font-size:0.72rem;color:{TEXT_MUTED};margin-left:6px">'
        f'{percentile}</span>'
    ) if percentile else ""
    return (
        f'<div style="display:flex;align-items:center;gap:12px;'
        f'background:{SURFACE};border:1px solid {BORDER};border-radius:8px;'
        f'padding:10px 14px;margin-bottom:6px">'
        f'<div style="font-size:0.75rem;font-weight:700;color:{TEXT_SECONDARY};'
        f'min-width:24px;text-align:center">#{rank}</div>'
        f'<div style="flex:1">'
        f'<div style="font-size:0.88rem;font-weight:600;color:{TEXT_PRIMARY}">{name}</div>'
        f'<div style="font-size:0.72rem;color:{team_color};font-weight:600">{team}</div>'
        f'</div>'
        f'<div style="text-align:right">'
        f'<div style="font-size:1.0rem;font-weight:700;color:{TEXT_PRIMARY}">'
        f'{metric_value}{pct_html}</div>'
        f'<div style="font-size:0.68rem;color:{TEXT_MUTED}">{metric_label}</div>'
        f'</div></div>'
    )


# ---------------------------------------------------------------------------
# HTML helpers: states
# ---------------------------------------------------------------------------

def loading_state(message: str = "Loading data…") -> str:
    return (
        f'<div style="text-align:center;padding:40px 20px;color:{TEXT_SECONDARY};'
        f'font-size:0.875rem">'
        f'<div style="font-size:1.5rem;margin-bottom:8px">⏳</div>{message}</div>'
    )


def error_state(title: str, message: str) -> str:
    return (
        f'<div style="background:rgba(239,68,68,0.07);border:1px solid rgba(239,68,68,0.3);'
        f'border-left:3px solid {ACCENT_RED};border-radius:8px;padding:16px 20px;margin:12px 0">'
        f'<div style="font-size:0.875rem;font-weight:700;color:{ACCENT_RED};'
        f'margin-bottom:4px">{title}</div>'
        f'<div style="font-size:0.82rem;color:{TEXT_SECONDARY};line-height:1.5">{message}</div>'
        f'</div>'
    )


def empty_state(title: str, message: str = "", icon: str = "📭") -> str:
    return (
        f'<div style="text-align:center;padding:48px 20px">'
        f'<div style="font-size:2rem;margin-bottom:10px">{icon}</div>'
        f'<div style="font-size:0.95rem;font-weight:600;color:{TEXT_SECONDARY};'
        f'margin-bottom:4px">{title}</div>'
        f'<div style="font-size:0.82rem;color:{TEXT_MUTED}">{message}</div>'
        f'</div>'
    )


def interpretation_card(text: str, accent: str = ACCENT) -> str:
    return (
        f'<div style="background:{SURFACE};border:1px solid {BORDER};'
        f'border-left:3px solid {accent};border-radius:8px;padding:16px 20px;margin:8px 0">'
        f'<div style="font-size:0.65rem;font-weight:700;letter-spacing:0.1em;'
        f'color:{TEXT_SECONDARY};text-transform:uppercase;margin-bottom:8px">'
        f'Analyst Interpretation</div>'
        f'<div style="font-size:0.88rem;color:{TEXT_SECONDARY};line-height:1.6">'
        f'{text}</div></div>'
    )


# ---------------------------------------------------------------------------
# Article-format helpers (backward compat)
# ---------------------------------------------------------------------------

def art_section(number: str, title: str) -> str:
    num_html = (
        f'<div class="art-num">{number}</div>'
    ) if number else ""
    return (
        f'<div class="art-section">'
        f'{num_html}'
        f'<div class="art-title">{title}</div>'
        f'</div>'
    )


def finding(text: str, variant: str = "") -> str:
    cls = f"finding-box {variant}".strip()
    return f'<div class="{cls}">{text}</div>'


def chart_caption(text: str) -> str:
    return (
        f'<div class="chart-caption" style="color:{TEXT_SECONDARY};'
        f'font-size:0.75rem;margin-top:6px;line-height:1.5">↑ {text}</div>'
    )


def interactive_well_open() -> str:
    return (
        '<div class="interactive-well">'
        '<div class="well-label">Interactive — try it yourself</div>'
    )


def interactive_well_close() -> str:
    return '</div>'
