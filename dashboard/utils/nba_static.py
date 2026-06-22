"""
Static NBA reference data: team colors, team IDs, and CDN URL helpers.
These do not require database access.
"""

from __future__ import annotations

# Primary brand colors for all 30 current NBA franchises
TEAM_COLORS: dict[str, str] = {
    "ATL": "#E03A3E", "BOS": "#007A33", "BKN": "#000000",
    "CHA": "#1D1160", "CHI": "#CE1141", "CLE": "#6F263D",
    "DAL": "#00538C", "DEN": "#0E2240", "DET": "#C8102E",
    "GSW": "#1D428A", "HOU": "#CE1141", "IND": "#002D62",
    "LAC": "#C8102E", "LAL": "#552583", "MEM": "#5D76A9",
    "MIA": "#98002E", "MIL": "#00471B", "MIN": "#0C2340",
    "NOP": "#0C2340", "NYK": "#006BB6", "OKC": "#007AC1",
    "ORL": "#0077C0", "PHI": "#006BB6", "PHX": "#1D1160",
    "POR": "#E03A3E", "SAC": "#5A2D81", "SAS": "#8A8D8F",
    "TOR": "#CE1141", "UTA": "#002B5C", "WAS": "#002B5C",
}

# Official NBA team IDs — needed to build logo URLs from the NBA CDN
TEAM_IDS: dict[str, int] = {
    "ATL": 1610612737, "BOS": 1610612738, "BKN": 1610612751,
    "CHA": 1610612766, "CHI": 1610612741, "CLE": 1610612739,
    "DAL": 1610612742, "DEN": 1610612743, "DET": 1610612765,
    "GSW": 1610612744, "HOU": 1610612745, "IND": 1610612754,
    "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763,
    "MIA": 1610612748, "MIL": 1610612749, "MIN": 1610612750,
    "NOP": 1610612740, "NYK": 1610612752, "OKC": 1610612760,
    "ORL": 1610612753, "PHI": 1610612755, "PHX": 1610612756,
    "POR": 1610612757, "SAC": 1610612758, "SAS": 1610612759,
    "TOR": 1610612761, "UTA": 1610612762, "WAS": 1610612764,
}

# Relocated/renamed teams that appear in historical data but no longer exist
HISTORICAL_TEAM_COLORS: dict[str, str] = {
    "NOH": "#002B5C",  # New Orleans Hornets → Pelicans
    "NJN": "#000000",  # New Jersey Nets → Brooklyn
    "SEA": "#00653A",  # Seattle SuperSonics → OKC
}


def team_logo_url(tricode: str) -> str | None:
    """Return the NBA CDN SVG logo URL for a team tricode, or None if unknown."""
    tid = TEAM_IDS.get(tricode)
    if tid is None:
        return None
    return f"https://cdn.nba.com/logos/nba/{tid}/global/L/logo.svg"


def player_headshot_url(person_id: int) -> str:
    """Return the NBA CDN headshot URL for a player ID (1040×760 crop)."""
    return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{person_id}.png"


def team_color(tricode: str, fallback: str = "#607D8B") -> str:
    """Return the primary brand color for a team tricode."""
    return (
        TEAM_COLORS.get(tricode)
        or HISTORICAL_TEAM_COLORS.get(tricode)
        or fallback
    )


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _wcag_luminance(r: int, g: int, b: int) -> float:
    def _lin(v: int) -> float:
        s = v / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _contrast_ratio(hex_fg: str, hex_bg: str) -> float:
    l1 = _wcag_luminance(*_hex_to_rgb(hex_fg))
    l2 = _wcag_luminance(*_hex_to_rgb(hex_bg))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def team_text_color(tricode: str, bg: str = "#18181B", min_contrast: float = 3.5) -> str:
    """Return the brand color lightened enough to be readable on `bg`.

    Blends toward white in 10% steps until the WCAG contrast ratio ≥ min_contrast.
    Falls back to white if no blend achieves it.
    """
    raw = team_color(tricode)
    if _contrast_ratio(raw, bg) >= min_contrast:
        return raw
    r, g, b = _hex_to_rgb(raw)
    for step in range(1, 11):
        blend = step * 0.1
        lr = int(r + (255 - r) * blend)
        lg = int(g + (255 - g) * blend)
        lb = int(b + (255 - b) * blend)
        candidate = f"#{lr:02X}{lg:02X}{lb:02X}"
        if _contrast_ratio(candidate, bg) >= min_contrast:
            return candidate
    return "#FFFFFF"
