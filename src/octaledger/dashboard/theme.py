"""Light/dark colour schemes and the two font sizes of the dashboard.

Streamlit cannot switch its native theme at runtime, so the schemes are applied as injected CSS
that recolours the app, the sidebar, inputs, buttons and tables, and sets ``color-scheme`` so
native browser widgets follow. The colour pairs below are chosen for **WCAG AA contrast**
(text on background >= 7:1, white/dark text on the primary colour >= 4.5:1); a unit test
computes the ratios so a future colour change cannot silently break readability.

Font size has exactly two steps (normal and large, as required): the root font size is set in
pixels and Streamlit's rem-based layout scales with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from octaledger.core.settings import FontSize, Theme

#: Root font size per step in pixels.
FONT_PIXELS: Final = {FontSize.NORMAL: 16, FontSize.LARGE: 20}


@dataclass(frozen=True, slots=True)
class Palette:
    """Colours of one scheme (all ``#RRGGBB``)."""

    background: str
    surface: str
    text: str
    muted: str
    primary: str
    on_primary: str
    border: str
    success: str
    warning: str
    danger: str
    plotly_template: str


PALETTES: Final = {
    Theme.LIGHT: Palette(
        background="#FFFFFF",
        surface="#F3F5F7",
        text="#1B1F23",
        muted="#4A5560",
        primary="#0B6BCB",
        on_primary="#FFFFFF",
        border="#C5CCD3",
        success="#1A7F37",
        warning="#8A5A00",
        danger="#B42318",
        plotly_template="plotly_white",
    ),
    Theme.DARK: Palette(
        background="#0E1117",
        surface="#1A1F29",
        text="#E6EAF0",
        muted="#B3BDC9",
        primary="#4DA3FF",
        on_primary="#0E1117",
        border="#3A424F",
        success="#56D364",
        warning="#E3B341",
        danger="#FF7B72",
        plotly_template="plotly_dark",
    ),
}


def css(theme: Theme, font_size: FontSize) -> str:
    """Return the ``<style>`` block for a theme and font size.

    Args:
        theme: ``Theme.LIGHT`` or ``Theme.DARK``.
        font_size: ``FontSize.NORMAL`` or ``FontSize.LARGE``.
    """
    p = PALETTES[theme]
    return f"""<style>
:root {{ color-scheme: {theme.value}; }}
html {{ font-size: {FONT_PIXELS[font_size]}px !important; }}
.stApp, [data-testid="stHeader"] {{ background-color: {p.background}; color: {p.text}; }}
[data-testid="stSidebar"], [data-testid="stSidebar"] > div {{ background-color: {p.surface}; }}
.stApp p, .stApp li, .stApp label, .stApp span, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp .stMarkdown, .stApp [data-testid="stMetricValue"], .stApp [data-testid="stMetricLabel"] {{
  color: {p.text};
}}
.stApp small, .stApp [data-testid="stCaptionContainer"] {{ color: {p.muted}; }}
.stApp input, .stApp textarea, .stApp [data-baseweb="select"] > div,
.stApp [data-baseweb="input"] {{
  background-color: {p.surface}; color: {p.text}; border-color: {p.border};
}}
.stApp button[kind="primary"] {{
  background-color: {p.primary}; color: {p.on_primary}; border-color: {p.primary};
}}
.stApp button[kind="secondary"] {{
  background-color: {p.surface}; color: {p.text}; border: 1px solid {p.border};
}}
.stApp [data-testid="stExpander"], .stApp [data-testid="stForm"] {{ border-color: {p.border}; }}
.ol-card {{
  background: {p.surface}; border: 1px solid {p.border}; border-radius: 0.6rem;
  padding: 0.9rem 1.1rem; margin-bottom: 0.8rem;
}}
.ol-big {{ font-size: 2rem; font-weight: 700; line-height: 1.2; }}
.ol-dot {{ display: inline-block; width: 0.8em; height: 0.8em; border-radius: 50%;
  margin-right: 0.4em; vertical-align: baseline; }}
.ol-ok {{ color: {p.success}; }} .ol-warn {{ color: {p.warning}; }} .ol-bad {{ color: {p.danger}; }}
</style>"""


def _linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(color: str) -> float:
    """Relative luminance of a ``#RRGGBB`` colour (WCAG 2.x)."""
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG contrast ratio (1..21) between two ``#RRGGBB`` colours."""
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)
