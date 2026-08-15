"""Chart palette and shared Plotly styling.

Colours are not hand-picked. Sentiment is *polarity*, so it takes a diverging
scale — two opposite hues with a neutral gray midpoint — not categorical hues.
Validated against the light surface #fcfcfb:

    CVD separation      worst pair ΔE 8.7  (target >= 8)   PASS
    Normal-vision floor worst pair ΔE 17.8 (floor >= 15)   PASS
    Contrast vs surface all 3 >= 3:1                       PASS

The chroma-floor check flags the neutral gray, which is correct and expected:
the midpoint of a diverging scale is *supposed* to read as "nothing". Every
chart here also ships direct labels and a table view, so colour never carries
meaning on its own.
"""

# --- surfaces & ink -------------------------------------------------------
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BORDER = "rgba(11,11,11,0.10)"

# --- diverging scale for sentiment ---------------------------------------
POSITIVE = "#2a78d6"     # blue  — cool pole
NEUTRAL = "#898781"      # gray  — reads as "nothing"
NEGATIVE = "#e34948"     # red   — warm pole

SENTIMENT_COLORS = {
    "positive": POSITIVE,
    "neutral": NEUTRAL,
    "negative": NEGATIVE,
    "unscored": "#c3c2b7",
}
# Order matters: negative | neutral | positive, so stacked bars read as a
# proper diverging scale left-to-right.
SENTIMENT_ORDER = ["negative", "neutral", "positive"]

# --- single-series magnitude (bars) --------------------------------------
SERIES_1 = "#2a78d6"

# Continuous diverging ramp for bubble fill (red -> gray -> blue).
DIVERGING_SCALE = [
    [0.0, "#e34948"],
    [0.5, "#d8d7d2"],
    [1.0, "#2a78d6"],
]

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def style_fig(fig, height: int = 320, showlegend: bool = False):
    """Apply shared chrome: recessive hairline grid, generous padding."""
    fig.update_layout(
        height=height,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT, size=13, color=INK_SECONDARY),
        margin=dict(l=8, r=16, t=8, b=8),
        showlegend=showlegend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, font=dict(size=12)),
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=AXIS,
                        font=dict(family=FONT, size=12, color=INK)),
    )
    fig.update_xaxes(showgrid=True, gridcolor=GRID, gridwidth=1,
                     zeroline=False, linecolor=AXIS, linewidth=1,
                     tickfont=dict(color=INK_MUTED, size=12))
    fig.update_yaxes(showgrid=True, gridcolor=GRID, gridwidth=1,
                     zeroline=False, linecolor=AXIS, linewidth=1,
                     tickfont=dict(color=INK_MUTED, size=12))
    return fig


CSS = f"""
<style>
  .block-container {{ padding-top: 2.2rem; max-width: 1280px; }}
  h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}

  .uk-hero {{
    border: 1px solid {BORDER}; border-radius: 12px; background: {SURFACE};
    padding: 18px 22px; margin-bottom: 6px;
  }}
  .uk-hero h1 {{ margin: 0 0 4px 0; font-size: 1.5rem; }}
  .uk-hero p {{ margin: 0; color: {INK_SECONDARY}; font-size: 0.92rem; }}

  /* The media-vs-public caveat. Deliberately prominent: this dashboard
     shows how NEWSPAPERS reported events, which is not public opinion. */
  .uk-caveat {{
    border: 1px solid {BORDER}; border-left: 3px solid {SERIES_1};
    border-radius: 8px; background: {SURFACE};
    padding: 12px 16px; margin: 14px 0 20px 0;
    color: {INK_SECONDARY}; font-size: 0.88rem; line-height: 1.5;
  }}
  .uk-caveat b {{ color: {INK}; }}

  /* Tabs — the primary navigation, so they carry real weight. */
  .stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
  .stTabs [data-testid="stTab"] {{
    font-size: 1.06rem !important; font-weight: 600 !important;
    padding: 12px 20px !important; border-radius: 9px 9px 0 0;
  }}
  .stTabs [data-testid="stTab"] p {{
    font-size: 1.06rem !important; font-weight: 600 !important;
    letter-spacing: -0.005em;
  }}
  .stTabs [data-testid="stTab"]:hover {{ background: {PAGE}; }}
  .stTabs [aria-selected="true"] p {{ color: {SERIES_1} !important; }}

  .uk-tiles {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }}
  .uk-tile {{
    flex: 1 1 150px; border: 1px solid {BORDER}; border-radius: 10px;
    background: {SURFACE}; padding: 14px 16px;
  }}
  .uk-tile .label {{
    font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em;
    color: {INK_MUTED}; margin-bottom: 6px;
  }}
  .uk-tile .value {{ font-size: 1.75rem; font-weight: 600; color: {INK};
                     line-height: 1.1; }}
  .uk-tile .sub {{ font-size: 0.78rem; color: {INK_SECONDARY}; margin-top: 3px; }}

  /* Stat tile: value + a small visual that carries real data (sparkline,
     meter or tone bar) — never decoration for its own sake. */
  .uk-stat {{
    border: 1px solid {BORDER}; border-radius: 11px; background: {SURFACE};
    padding: 0; overflow: hidden; height: 100%;
  }}
  .uk-stat .accent {{ height: 3px; width: 100%; }}
  .uk-stat .inner {{ padding: 13px 16px 14px 16px; }}
  .uk-stat .label {{
    font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.07em;
    color: {INK_MUTED}; display: flex; align-items: center; gap: 5px;
  }}
  .uk-stat .value {{
    font-size: 2.1rem; font-weight: 650; color: {INK}; line-height: 1.05;
    margin-top: 5px; overflow-wrap: anywhere;
  }}
  .uk-stat .value.mid {{ font-size: 1.5rem; }}
  .uk-stat .value.long {{ font-size: 1.12rem; line-height: 1.25; }}
  .uk-stat .sub {{ font-size: 0.76rem; color: {INK_SECONDARY}; margin-top: 3px; }}
  .uk-stat .viz {{ margin-top: 9px; height: 30px; }}
  .uk-stat .viz svg {{ display: block; width: 100%; height: 30px; }}

  /* Card titles. The border comes from st.container(border=True) — an HTML
     div opened via st.markdown cannot wrap Streamlit elements, so it would
     close immediately and box only the heading. */
  .uk-card-h {{ margin: 0 0 2px 0; font-size: 0.95rem; font-weight: 600;
                color: {INK}; }}
  .uk-card-s {{ font-size: 0.8rem; color: {INK_MUTED}; margin-bottom: 8px;
                line-height: 1.45; }}

  /* Big emoji sentiment summary */
  .uk-faces {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .uk-face {{
    flex: 1 1 130px; border: 1px solid {BORDER}; border-radius: 10px;
    background: {SURFACE}; padding: 14px 12px 12px 12px; text-align: center;
  }}
  .uk-face .emoji {{ font-size: 2rem; line-height: 1.1; }}
  .uk-face .pct {{ font-size: 1.5rem; font-weight: 650; margin-top: 2px; }}
  .uk-face .lbl {{ font-size: 0.78rem; color: {INK_SECONDARY};
                   text-transform: capitalize; }}
  .uk-face .cnt {{ font-size: 0.72rem; color: {INK_MUTED}; margin-top: 2px; }}

  /* Compact variant for the graph's side panel — at full size the three
     faces wrap onto two rows in a one-third-width column. */
  .uk-faces.compact {{ gap: 7px; }}
  .uk-faces.compact .uk-face {{ flex: 1 1 62px; padding: 8px 4px 7px 4px; }}
  .uk-faces.compact .emoji {{ font-size: 1.25rem; }}
  .uk-faces.compact .pct {{ font-size: 1.02rem; }}
  .uk-faces.compact .lbl {{ font-size: 0.66rem; }}
  .uk-faces.compact .cnt {{ font-size: 0.62rem; }}

  /* Article card with thumbnail */
  .uk-card-art {{
    display: flex; gap: 14px; align-items: flex-start;
    border: 1px solid {BORDER}; border-radius: 10px; background: {SURFACE};
    padding: 10px; margin-bottom: 10px;
  }}
  .uk-card-art .thumb {{
    width: 116px; height: 78px; flex: 0 0 116px; border-radius: 7px;
    display: flex; align-items: center; justify-content: center;
    color: {INK_SECONDARY}; font-size: 1.5rem; font-weight: 700;
    overflow: hidden;
  }}
  .uk-card-art .body {{ flex: 1 1 auto; min-width: 0; }}
  .uk-card-art a {{
    color: {INK}; text-decoration: none; font-weight: 600;
    font-size: 0.94rem; line-height: 1.35; display: block;
  }}
  .uk-card-art a:hover {{ color: {SERIES_1}; text-decoration: underline; }}
  .uk-card-art .meta {{ font-size: 0.76rem; color: {INK_MUTED};
                        margin: 5px 0 7px 0; }}
  .uk-card-art .tags {{ display: flex; gap: 6px; flex-wrap: wrap;
                        align-items: center; }}
  .uk-tag {{
    display: inline-block; padding: 1px 8px; border-radius: 999px;
    font-size: 0.7rem; color: {INK_SECONDARY};
    background: {PAGE}; border: 1px solid {BORDER};
  }}

  .uk-art {{
    border-bottom: 1px solid {GRID}; padding: 10px 0;
  }}
  .uk-art a {{ color: {INK}; text-decoration: none; font-weight: 550;
               font-size: 0.92rem; }}
  .uk-art a:hover {{ text-decoration: underline; color: {SERIES_1}; }}
  .uk-art .meta {{ font-size: 0.76rem; color: {INK_MUTED}; margin-top: 3px; }}
  .uk-pill {{
    display: inline-block; padding: 1px 8px; border-radius: 999px;
    font-size: 0.7rem; font-weight: 600; margin-right: 6px;
  }}
</style>
"""


# Emoji reinforce the sentiment reading for a non-technical audience, but they
# are a THIRD channel, never the only one: every pill carries emoji + colour +
# the written label, so it survives colour-blindness and emoji-font gaps alike.
SENTIMENT_EMOJI = {
    "positive": "🙂",
    "neutral": "😐",
    "negative": "😠",
    "unscored": "❔",
}


def sentiment_pill(label: str, score=None) -> str:
    """Emoji + colour + text together — never any one of them alone."""
    color = SENTIMENT_COLORS.get(label, INK_MUTED)
    emoji = SENTIMENT_EMOJI.get(label, "❔")
    val = ""
    if score is not None:
        try:
            val = f" {float(score):+.2f}"
        except (TypeError, ValueError):
            val = ""
    return (f'<span class="uk-pill" style="background:{color}1f;color:{color};">'
            f'{emoji} {label}{val}</span>')


def sentiment_face(label: str, pct: float, count: int) -> str:
    """Big emoji + number tile, for the at-a-glance sentiment summary."""
    color = SENTIMENT_COLORS.get(label, INK_MUTED)
    emoji = SENTIMENT_EMOJI.get(label, "❔")
    return (f'<div class="uk-face" style="border-top:3px solid {color};">'
            f'<div class="emoji">{emoji}</div>'
            f'<div class="pct" style="color:{color};">{pct:.0f}%</div>'
            f'<div class="lbl">{label}</div>'
            f'<div class="cnt">{count} articles</div></div>')


def _placeholder(seed: str) -> str:
    """Deterministic tinted block when an article has no og:image."""
    tints = ["#dce9fb", "#fbe3d8", "#d7f0e6", "#f7e7c4", "#e7e2f5"]
    return tints[sum(ord(c) for c in (seed or "x")) % len(tints)]


def article_card(title: str, url: str, publisher: str, day, label: str,
                 score=None, image: str = "", language: str = "",
                 districts: str = "", aspects: str = "") -> str:
    """One article as a visual card: thumbnail, headline, source, sentiment."""
    title = (title or "(untitled)").replace("<", "&lt;")
    if image:
        thumb = (f'<div class="thumb" style="background-image:url(\'{image}\');'
                 f'background-size:cover;background-position:center;"></div>')
    else:
        thumb = (f'<div class="thumb" style="background:{_placeholder(publisher)};">'
                 f'<span>{(publisher or "?")[:1].upper()}</span></div>')

    tags = ""
    for t in [x for x in (districts or "").split("|") if x][:2]:
        tags += f'<span class="uk-tag">📍 {t}</span>'
    for t in [x for x in (aspects or "").split("|") if x][:2]:
        tags += f'<span class="uk-tag">🏷️ {t}</span>'

    return (
        f'<div class="uk-card-art">{thumb}'
        f'<div class="body">'
        f'<a href="{url}" target="_blank" rel="noopener">{title}</a>'
        f'<div class="meta">{publisher or "—"} · {day} · {language}</div>'
        f'<div class="tags">{sentiment_pill(label, score)}{tags}</div>'
        f'</div></div>')


def tile(label: str, value, sub: str = "") -> str:
    return (f'<div class="uk-tile"><div class="label">{label}</div>'
            f'<div class="value">{value}</div>'
            f'<div class="sub">{sub}</div></div>')


# --- small inline visuals for stat tiles ---------------------------------
# Inline SVG rather than a chart library: these are 30px tall, have no axes,
# and must not cost a Plotly round-trip each.

def sparkline(values, color: str = SERIES_1, width: int = 240,
              height: int = 30) -> str:
    """Area + line sparkline. Shows shape over time, not exact values."""
    vals = [float(v) for v in values if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    step = width / (len(vals) - 1)
    pad = 3
    pts = [(i * step, height - pad - (v - lo) / span * (height - 2 * pad))
           for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,{height} {line} {width},{height}"
    last_x, last_y = pts[-1]
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'role="img" aria-label="trend over time">'
        f'<polygon points="{area}" fill="{color}" opacity="0.12"/>'
        f'<polyline points="{line}" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3" fill="{color}"/>'
        f'</svg>')


def meter(pct: float, color: str = SERIES_1, height: int = 30) -> str:
    """Single ratio against a limit — a meter, not a two-slice pie."""
    pct = max(0.0, min(100.0, float(pct)))
    return (
        f'<svg viewBox="0 0 240 {height}" preserveAspectRatio="none" '
        f'role="img" aria-label="{pct:.0f} percent">'
        f'<rect x="0" y="{height/2-4}" width="240" height="8" rx="4" '
        f'fill="{GRID}"/>'
        f'<rect x="0" y="{height/2-4}" width="{pct*2.4:.1f}" height="8" rx="4" '
        f'fill="{color}"/></svg>')


def tone_bar(neg: int, neu: int, pos: int, height: int = 30) -> str:
    """Mini diverging stacked bar: negative | neutral | positive."""
    total = max(neg + neu + pos, 1)
    w = [v / total * 240 for v in (neg, neu, pos)]
    colors = [NEGATIVE, NEUTRAL, POSITIVE]
    out, x = [], 0.0
    for width, color in zip(w, colors):
        if width > 0:
            out.append(f'<rect x="{x:.1f}" y="{height/2-5}" '
                       f'width="{max(width - 2, 1):.1f}" height="10" rx="2" '
                       f'fill="{color}"/>')
        x += width
    return (f'<svg viewBox="0 0 240 {height}" preserveAspectRatio="none" '
            f'role="img" aria-label="tone split">{"".join(out)}</svg>')


def stat_tile(label: str, value, sub: str = "", accent: str = SERIES_1,
              viz: str = "") -> str:
    """Headline number with an accent rule and an optional inline visual.

    Long text values (an issue name rather than a count) step down a size so
    they wrap inside the tile instead of overflowing it.
    """
    body = f'<div class="viz">{viz}</div>' if viz else ""
    text = str(value)
    cls = "value" + (" long" if len(text) > 13 else
                     " mid" if len(text) > 8 else "")
    return (
        f'<div class="uk-stat">'
        f'<div class="accent" style="background:{accent};"></div>'
        f'<div class="inner">'
        f'<div class="label">{label}</div>'
        f'<div class="{cls}">{text}</div>'
        f'<div class="sub">{sub}</div>'
        f'{body}</div></div>')
