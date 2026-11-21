"""Design system of the dashboard: colours, typography, shapes, light/dark and two font sizes.

The decisions below come from the GUI research documented in ``docs/GUI_KONZEPT.md``:

* **Calm and neutral** - one primary colour, a neutral grey scale and three status colours.
  Strong colour is reserved for what carries meaning (the colours of the activities).
* **Cards instead of shadows** - 1 px borders and light/dark surface steps; shadows do not work in
  dark mode. Radii: 8 px for controls, 12 px for cards.
* **Inter** (variable, self-hosted) with ``system-ui`` fallbacks; weights 400/500/600 only;
  tabular figures for every number so running timers do not jitter.
* **No pure black/white** in dark mode, accents lighter and desaturated.
* **WCAG 2.2 AA**: text >= 7:1 (AAA) on its surface, muted text and status colours >= 4.5:1,
  borders of inputs >= 3:1, a visible focus ring. A unit test computes every ratio so a future
  colour change cannot silently break readability.

Streamlit cannot switch its native theme at runtime, so the schemes are injected as CSS. Selectors
prefer ``data-testid`` and the ``st-key-*`` classes Streamlit adds for widget keys; both are more
stable than generated class names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from octaledger.core.settings import FontSize, Theme

#: Root font size per step in pixels (exactly two steps, as required).
FONT_PIXELS: Final = {FontSize.NORMAL: 16, FontSize.LARGE: 20}

#: Self-hosted font file served by Streamlit static serving (``dashboard/static``).
FONT_URL: Final = "app/static/Inter-Variable.woff2"
FONT_STACK: Final = (
    '"Inter", system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
)


@dataclass(frozen=True, slots=True)
class Palette:
    """Colours of one scheme (all ``#RRGGBB``)."""

    background: str  # page
    surface: str  # cards, sidebar, inputs
    text: str
    muted: str
    primary: str
    on_primary: str
    border: str  # decorative card borders
    input_border: str  # borders of interactive controls (>= 3:1)
    success: str
    warning: str
    danger: str
    plotly_template: str


PALETTES: Final = {
    Theme.LIGHT: Palette(
        background="#F7F8FA",
        surface="#FFFFFF",
        text="#1F2937",
        muted="#4B5563",
        primary="#2563EB",
        on_primary="#FFFFFF",
        border="#D0D5DD",
        input_border="#8A94A3",
        success="#067647",
        warning="#B54708",
        danger="#B42318",
        plotly_template="plotly_white",
    ),
    Theme.DARK: Palette(
        background="#14171C",
        surface="#1C2027",
        text="#E6E9EE",
        muted="#A3ABB8",
        primary="#8CB4FF",
        on_primary="#0B1220",
        border="#3C4350",
        input_border="#6C7686",
        success="#4ADE80",
        warning="#FBBF24",
        danger="#FF8A80",
        plotly_template="plotly_dark",
    ),
}


def native_theme_options(theme: Theme) -> dict[str, str]:
    """Streamlit's own theme options for a scheme.

    CSS alone cannot recolour everything: tables are drawn on a canvas, and pop-ups, date pickers,
    sliders and tabs take their colours from Streamlit's *native* theme, which otherwise follows the
    operating system (dark OS + light dashboard = dark fields with dark text). Setting the native
    theme to the same palette keeps those parts consistent with the CSS in :func:`css`.
    """
    p = PALETTES[theme]
    return {
        "theme.base": theme.value,
        "theme.primaryColor": p.primary,
        "theme.backgroundColor": p.background,
        "theme.secondaryBackgroundColor": p.surface,
        "theme.textColor": p.text,
        "theme.borderColor": p.border,
        "theme.sidebar.backgroundColor": p.surface,
        "theme.sidebar.secondaryBackgroundColor": p.background,
    }


def apply_native_theme(theme: Theme) -> bool:
    """Set Streamlit's native theme; return ``True`` if it changed.

    Streamlit sends its theme to the browser when a script run *starts*, so a change made during a
    run only reaches the browser with the next run. The caller therefore reruns once on ``True``.
    """
    from streamlit import config

    changed = False
    for key, value in native_theme_options(theme).items():
        if config.get_option(key) != value:
            config.set_option(key, value)
            changed = True
    return changed


def css(theme: Theme, font_size: FontSize) -> str:
    """Return the ``<style>`` block for a theme and font size.

    Args:
        theme: ``Theme.LIGHT`` or ``Theme.DARK``.
        font_size: ``FontSize.NORMAL`` or ``FontSize.LARGE``.
    """
    p = PALETTES[theme]
    return f"""<style>
@font-face {{
  font-family: "Inter"; font-style: normal; font-weight: 100 900; font-display: swap;
  src: url("{FONT_URL}") format("woff2");
}}
:root {{ color-scheme: {theme.value}; }}
html {{ font-size: {FONT_PIXELS[font_size]}px !important; }}
html, body, .stApp, .stApp button, .stApp input, .stApp textarea, .stApp select {{
  font-family: {FONT_STACK};
}}
.stApp, [data-testid="stHeader"] {{
  background-color: {p.background}; color: {p.text}; line-height: 1.5;
}}
[data-testid="stMainBlockContainer"] {{ max-width: 1200px; padding-top: 2rem; }}
[data-testid="stSidebar"], [data-testid="stSidebar"] > div {{
  background-color: {p.surface}; border-right: 1px solid {p.border};
}}
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{
  color: {p.text}; font-weight: 600; line-height: 1.25;
}}
.stApp h2 {{ font-size: 1.6rem; margin-bottom: 0.25rem; }}
.stApp h3 {{ font-size: 1.2rem; }}
.stApp p, .stApp li, .stApp label, .stApp span, .stApp .stMarkdown,
.stApp [data-testid="stMetricLabel"] {{ color: {p.text}; }}
.stApp label, .stApp [data-testid="stMetricLabel"] {{ font-weight: 500; }}
.stApp small, .stApp [data-testid="stCaptionContainer"] {{ color: {p.muted}; }}
.stApp [data-testid="stMetricValue"], .ol-big, .ol-num {{
  color: {p.text}; font-variant-numeric: tabular-nums; font-feature-settings: "tnum" 1;
}}
.stApp [data-testid="stMetricValue"] {{ font-weight: 600; }}

/* Controls: 8 px radius, 3:1 borders, visible focus. */
.stApp input, .stApp textarea, .stApp [data-baseweb="select"] > div,
.stApp [data-baseweb="input"] {{
  background-color: {p.surface}; color: {p.text}; border-color: {p.input_border};
  border-radius: 8px;
}}
.stApp button {{ border-radius: 8px; font-weight: 500; }}
.stApp button[kind="primary"], .stApp button[kind="primaryFormSubmit"] {{
  background-color: {p.primary}; color: {p.on_primary}; border: 1px solid {p.primary};
}}
.stApp button[kind="primary"] *, .stApp button[kind="primaryFormSubmit"] * {{
  color: {p.on_primary};
}}
.stApp button[kind="secondaryFormSubmit"] {{
  background-color: {p.surface}; color: {p.text}; border: 1px solid {p.input_border};
}}
.stApp button[kind="secondary"] {{
  background-color: {p.surface}; color: {p.text}; border: 1px solid {p.input_border};
}}
.stApp button[kind="tertiary"] {{ color: {p.primary}; }}
.stApp :focus-visible {{ outline: 3px solid {p.primary} !important; outline-offset: 2px; }}

/* Cards: bordered containers, expanders and forms share one look (no shadows). */
.stApp [data-testid="stVerticalBlockBorderWrapper"] {{ border-color: {p.border}; }}
.stApp [data-testid="stExpander"], .stApp [data-testid="stForm"] {{
  border: 1px solid {p.border}; border-radius: 12px; background-color: {p.surface};
}}
.stApp [data-testid="stAlert"] {{ border-radius: 12px; }}
.st-key-statusbar {{
  background-color: {p.surface}; border: 1px solid {p.border}; border-radius: 12px;
  padding: 0.6rem 1rem;
}}

/* Sidebar navigation: grouped text+icon buttons, the active page is filled. */
.ol-nav-group {{
  color: {p.muted}; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.06em;
  text-transform: uppercase; margin: 1rem 0 0.25rem 0.25rem;
}}
[class*="st-key-nav_"] button {{
  justify-content: flex-start; text-align: left; width: 100%;
}}
[class*="st-key-nav_"] button[kind="secondary"] {{
  background: transparent; border: 1px solid transparent; color: {p.text};
}}
[class*="st-key-nav_"] button[kind="secondary"]:hover {{ border-color: {p.input_border}; }}
[class*="st-key-nav_"] button[kind="primary"] {{ font-weight: 600; }}

/* Helper classes used by pages. */
.ol-card {{
  background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px;
  padding: 0.9rem 1.1rem; margin-bottom: 0.8rem;
}}
.ol-big {{ font-size: 2rem; font-weight: 600; line-height: 1.2; }}
.ol-dot {{ display: inline-block; width: 0.8em; height: 0.8em; border-radius: 50%;
  margin-right: 0.4em; vertical-align: baseline; }}
.ol-ok {{ color: {p.success}; }} .ol-warn {{ color: {p.warning}; }} .ol-bad {{ color: {p.danger}; }}
.ol-muted {{ color: {p.muted}; }}
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
