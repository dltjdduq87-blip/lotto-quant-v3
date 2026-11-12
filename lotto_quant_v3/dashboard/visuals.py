"""Visual layer for the dashboard: theme CSS, glossy balls, hero, animated widgets.

Everything here returns HTML/CSS strings. Pieces that need JavaScript (the draw machine and the
count-up strip) are meant for `streamlit.components.v1.html`; the rest goes through
`st.markdown(..., unsafe_allow_html=True)`.

Motion rules used throughout: only transform/opacity are animated, entrances are short
ease-out moves, and everything is switched off under `prefers-reduced-motion`.
"""
from __future__ import annotations

import json

BALL_COLORS = {
    range(1, 11): "#fbc400",
    range(11, 21): "#69c8f2",
    range(21, 31): "#ff7272",
    range(31, 41): "#aaaaaa",
    range(41, 46): "#b0d840",
}

# Validated dark-mode palette (dataviz reference instance -- dark column).
VIZ = {
    "surface": "#1a1a19",
    "page": "#0d0d0d",
    "ink": "#ffffff",
    "ink_muted": "#c3c2b7",
    "axis_muted": "#898781",
    "grid": "#2c2c2a",
    "accent": "#3987e5",
    "accent_soft": "#69c8f2",
    "good": "#0ca30c",
    "critical": "#e66767",
    "gold": "#fab219",
}

FONT_STACK = '"Source Sans Pro","Source Sans 3",-apple-system,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",sans-serif'


def ball_color(n: int) -> str:
    for rng, color in BALL_COLORS.items():
        if n in rng:
            return color
    return "#333333"


GLOBAL_CSS = """
<style>
@keyframes lqv-rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
@keyframes lqv-fade { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@keyframes lqv-pop {
  0% { opacity: 0; transform: translateY(-18px) scale(.4); }
  65% { opacity: 1; transform: translateY(2px) scale(1.08); }
  100% { opacity: 1; transform: none; }
}
@keyframes lqv-float { 0%, 100% { transform: translateY(0) rotate(0deg); } 50% { transform: translateY(-9px) rotate(6deg); } }
@keyframes lqv-aurora {
  0% { transform: translate3d(-4%, -3%, 0) scale(1); }
  100% { transform: translate3d(5%, 4%, 0) scale(1.12); }
}
@keyframes lqv-shimmer { from { background-position: 0% 50%; } to { background-position: 200% 50%; } }
@keyframes lqv-slide { from { left: 0%; opacity: 0; } to { left: var(--to); opacity: 1; } }
@keyframes lqv-grow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes lqv-ring { 0% { box-shadow: 0 0 0 0 rgba(250,178,25,.55); } 100% { box-shadow: 0 0 0 12px rgba(250,178,25,0); } }

/* page plane with a slow aurora behind everything */
.stApp { background: __PAGE__; }
.stApp::before {
  content: ""; position: fixed; inset: -20%; z-index: 0; pointer-events: none;
  background:
    radial-gradient(38% 34% at 22% 24%, rgba(57,135,229,.20), transparent 70%),
    radial-gradient(32% 30% at 80% 16%, rgba(250,178,25,.10), transparent 70%),
    radial-gradient(40% 36% at 70% 82%, rgba(105,200,242,.11), transparent 70%);
  animation: lqv-aurora 26s ease-in-out infinite alternate;
}
[data-testid="stAppViewContainer"] { position: relative; z-index: 1; background: transparent; }
[data-testid="stHeader"] { background: transparent; }

/* metric cards: glass, staggered entrance, lift on hover */
[data-testid="stMetric"] {
  background: linear-gradient(160deg, rgba(38,38,36,.92), rgba(22,22,21,.92));
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 14px;
  padding: 14px 16px;
  box-shadow: 0 6px 18px rgba(0,0,0,.28);
  animation: lqv-rise .5s cubic-bezier(.2,.8,.2,1) both;
  transition: transform .18s ease-out, border-color .18s ease-out, box-shadow .18s ease-out;
}
[data-testid="stMetric"]:hover {
  transform: translateY(-3px);
  border-color: rgba(57,135,229,.55);
  box-shadow: 0 12px 26px rgba(0,0,0,.4), 0 0 0 1px rgba(57,135,229,.18);
}
[data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] { animation-delay: .07s; }
[data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] { animation-delay: .14s; }
[data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] { animation-delay: .21s; }
[data-testid="stMetricLabel"] { color: __INK_MUTED__; }
[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }

/* tabs */
[data-testid="stTabs"] button[role="tab"] {
  font-weight: 600; color: __INK_MUTED__;
  transition: color .15s ease-out, transform .15s ease-out;
}
[data-testid="stTabs"] button[role="tab"]:hover { color: __INK__; transform: translateY(-1px); }
[data-testid="stTabs"] button[aria-selected="true"] { color: __INK__; }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
  background: linear-gradient(90deg, __ACCENT__, __ACCENT_SOFT__); height: 3px; border-radius: 3px;
}
[data-testid="stTabs"] [role="tabpanel"] { animation: lqv-fade .32s ease-out both; }

/* buttons */
.stButton > button, .stDownloadButton > button {
  border-radius: 10px; border: 1px solid rgba(255,255,255,0.14);
  transition: transform .12s ease-out, box-shadow .18s ease-out, border-color .18s ease-out;
}
.stButton > button:hover { border-color: rgba(105,200,242,.7); box-shadow: 0 6px 18px rgba(57,135,229,.22); transform: translateY(-1px); }
.stButton > button:active { transform: scale(.97); }
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, __ACCENT__, #2a6bd0); border: none;
  box-shadow: 0 6px 20px rgba(57,135,229,.35);
}
.stButton > button[kind="primary"]:hover { box-shadow: 0 10px 28px rgba(57,135,229,.5); }

/* charts and tables settle in */
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"], [data-testid="stTable"] {
  animation: lqv-fade .45s ease-out both; border-radius: 12px; overflow: hidden;
}
hr { border-color: __GRID__ !important; }

/* hero */
.lqv-hero {
  position: relative; overflow: hidden;
  background: linear-gradient(135deg, rgba(26,26,25,.96) 0%, rgba(18,35,59,.96) 100%);
  border: 1px solid rgba(255,255,255,0.09); border-radius: 18px;
  padding: 26px 28px; margin-bottom: 12px;
  animation: lqv-rise .55s cubic-bezier(.2,.8,.2,1) both;
}
.lqv-hero h1 { margin: 0 0 6px 0; padding: 0; font-size: 1.85rem; line-height: 1.2; }
.lqv-hero h1 .lqv-grad {
  background: linear-gradient(90deg, __INK__, __ACCENT_SOFT__, __GOLD__, __INK__);
  background-size: 200% 100%;
  -webkit-background-clip: text; background-clip: text; color: transparent;
  animation: lqv-shimmer 9s linear infinite;
}
.lqv-hero p { margin: 0; color: __INK_MUTED__; font-size: .95rem; max-width: 46rem; }
.lqv-hero.has-balls { padding-right: 360px; }
.lqv-hero-balls { position: absolute; right: 22px; top: 50%; margin-top: -26px; display: flex; gap: 8px; opacity: .92; }
.lqv-hero-balls .lqv-ball { animation: lqv-float 4.6s ease-in-out infinite; animation-delay: calc(var(--i) * -.55s); }
@media (max-width: 1100px) { .lqv-hero-balls { display: none; } .lqv-hero.has-balls { padding-right: 28px; } }

/* glossy balls */
.lqv-balls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 4px 0 10px; }
.lqv-ball {
  --s: 46px;
  width: var(--s); height: var(--s); border-radius: 50%; flex: 0 0 auto;
  display: inline-flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 800; font-size: calc(var(--s) * .4); font-variant-numeric: tabular-nums;
  text-shadow: 0 1px 2px rgba(0,0,0,.5);
  background:
    radial-gradient(circle at 32% 26%, rgba(255,255,255,.85) 0 7%, rgba(255,255,255,.22) 22%, transparent 42%),
    radial-gradient(circle at 70% 80%, rgba(0,0,0,.34), transparent 58%),
    var(--c);
  box-shadow: 0 5px 10px rgba(0,0,0,.45), inset 0 -3px 6px rgba(0,0,0,.22);
  animation: lqv-pop .5s cubic-bezier(.34,1.4,.64,1) both;
  animation-delay: calc(var(--i, 0) * 70ms);
  transition: transform .15s ease-out;
}
.lqv-balls .lqv-ball:hover { transform: translateY(-4px) scale(1.06); }
.lqv-ball.bonus { outline: 2px solid rgba(255,255,255,.75); outline-offset: 2px; }
.lqv-plus { color: __AXIS__; font-size: 22px; font-weight: 700; margin: 0 2px; }

/* generic info card */
.lqv-card {
  background: linear-gradient(160deg, rgba(38,38,36,.92), rgba(22,22,21,.92));
  border: 1px solid rgba(255,255,255,.10); border-radius: 16px; padding: 18px 20px; margin: 6px 0 12px;
  animation: lqv-rise .5s cubic-bezier(.2,.8,.2,1) both;
}
.lqv-card h4 { margin: 0 0 4px; padding: 0; font-size: .86rem; font-weight: 600; color: __INK_MUTED__; }
.lqv-big { font-size: 2rem; font-weight: 800; color: __INK__; line-height: 1.15; font-variant-numeric: tabular-nums; }
.lqv-sub { color: __INK_MUTED__; font-size: .9rem; margin-top: 4px; }
.lqv-up { color: #5fd35f; font-weight: 700; }
.lqv-down { color: __CRITICAL__; font-weight: 700; }

/* share meter */
.lqv-meter { position: relative; height: 62px; margin: 30px 6px 34px; }
.lqv-meter-track {
  position: absolute; left: 0; right: 0; top: 24px; height: 14px; border-radius: 8px;
  background: linear-gradient(90deg, #3987e5 0%, #2c2c2a 48%, #e66767 100%);
  transform-origin: left center; animation: lqv-grow .7s cubic-bezier(.2,.8,.2,1) both;
}
.lqv-meter-avg { position: absolute; top: 14px; height: 34px; width: 2px; background: rgba(255,255,255,.75); }
.lqv-meter-avg span, .lqv-meter-end {
  position: absolute; top: 40px; font-size: .78rem; color: __INK_MUTED__; white-space: nowrap;
}
.lqv-meter-avg span { transform: translateX(-50%); }
.lqv-meter-end.l { left: 0; } .lqv-meter-end.r { right: 0; }
.lqv-meter-dot {
  position: absolute; top: 13px; width: 36px; height: 36px; margin-left: -18px; border-radius: 50%;
  background: radial-gradient(circle at 32% 28%, #fff 0 12%, __GOLD__ 46%, #b97d05 100%);
  border: 2px solid #fff; box-shadow: 0 4px 12px rgba(0,0,0,.5);
  left: var(--to); animation: lqv-slide 1s cubic-bezier(.2,.9,.25,1) both, lqv-ring 1.4s ease-out 1s 2;
}
.lqv-meter-dot span {
  position: absolute; left: 50%; bottom: 42px; transform: translateX(-50%);
  background: __GOLD__; color: #1a1300; font-weight: 800; font-size: .82rem;
  padding: 2px 8px; border-radius: 8px; white-space: nowrap;
}

/* number popularity grid */
.lqv-grid { display: grid; grid-template-columns: repeat(9, minmax(0, 1fr)); gap: 6px; margin: 8px 0 4px; }
.lqv-cell {
  border-radius: 10px; padding: 7px 0 6px; text-align: center; color: #fff;
  background: var(--bg); border: 1px solid rgba(255,255,255,.08);
  animation: lqv-fade .4s ease-out both; animation-delay: calc(var(--i) * 12ms);
  transition: transform .15s ease-out;
}
.lqv-cell:hover { transform: scale(1.07); }
.lqv-cell b { display: block; font-size: 1.02rem; line-height: 1.1; }
.lqv-cell small { font-size: .7rem; opacity: .85; font-variant-numeric: tabular-nums; }
.lqv-legend { display: flex; justify-content: space-between; font-size: .78rem; color: __INK_MUTED__; margin-bottom: 10px; }
@media (max-width: 640px) { .lqv-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); } }

@media (prefers-reduced-motion: reduce) {
  .stApp::before, .lqv-hero, .lqv-hero h1 .lqv-grad, .lqv-ball, .lqv-card, .lqv-cell, .lqv-meter-track, .lqv-meter-dot,
  [data-testid="stMetric"], [data-testid="stTabs"] [role="tabpanel"],
  [data-testid="stPlotlyChart"], [data-testid="stDataFrame"], [data-testid="stTable"] {
    animation: none !important; transition: none !important;
  }
}
</style>
"""


def global_css() -> str:
    css = GLOBAL_CSS
    for key, token in (("page", "__PAGE__"), ("ink_muted", "__INK_MUTED__"), ("ink", "__INK__"),
                       ("accent_soft", "__ACCENT_SOFT__"), ("accent", "__ACCENT__"), ("grid", "__GRID__"),
                       ("gold", "__GOLD__"), ("axis_muted", "__AXIS__"), ("critical", "__CRITICAL__")):
        css = css.replace(token, VIZ[key])
    return css


def _ball(n: int, i: int, size: int, extra: str = "") -> str:
    return (f'<span class="lqv-ball{extra}" style="--c:{ball_color(n)};--i:{i};--s:{size}px" '
            f'aria-label="{n}">{n}</span>')


def render_balls(numbers, bonus: int | None = None, size: int = 46) -> str:
    html = "".join(_ball(int(n), i, size) for i, n in enumerate(numbers))
    if bonus is not None:
        html += '<span class="lqv-plus">+</span>' + _ball(int(bonus), len(list(numbers)) + 1, size, " bonus")
    return f'<div class="lqv-balls">{html}</div>'


def hero(emoji: str, title: str, subtitle: str, balls=(7, 14, 23, 31, 38, 44)) -> str:
    deco = "".join(_ball(n, i, 44) for i, n in enumerate(balls))
    return (f'<div class="lqv-hero has-balls"><div class="lqv-hero-balls" aria-hidden="true">{deco}</div>'
            f'<h1>{emoji} <span class="lqv-grad">{title}</span></h1><p>{subtitle}</p></div>')


def card(label: str, big: str, sub: str = "") -> str:
    return f'<div class="lqv-card"><h4>{label}</h4><div class="lqv-big">{big}</div><div class="lqv-sub">{sub}</div></div>'


def share_meter(multiplier: float, floor: float, top: float) -> str:
    """Horizontal meter: where a ticket sits between the least and most shared combinations."""
    span = top - floor

    def pos(v: float) -> float:
        return min(max((v - floor) / span, 0.0), 1.0) * 100

    return (
        '<div class="lqv-meter">'
        '<div class="lqv-meter-track"></div>'
        f'<div class="lqv-meter-avg" style="left:{pos(1.0):.1f}%"><span>평균 조합</span></div>'
        '<span class="lqv-meter-end l">덜 나눠 가짐</span><span class="lqv-meter-end r">많이 나눠 가짐</span>'
        f'<div class="lqv-meter-dot" style="--to:{pos(multiplier):.1f}%"><span>내 번호 {multiplier:.2f}배</span></div>'
        '</div>'
    )


def _mix(a: str, b: str, t: float) -> str:
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(pa, pb))


def popularity_grid(index) -> str:
    """45 tiles coloured on a diverging scale: blue = chosen less than average, red = more."""
    values = [float(v) for v in index]
    spread = max(abs(v - 100) for v in values) or 1.0
    cells = []
    for i, v in enumerate(values):
        t = (v - 100) / spread
        bg = _mix("#2c2c2a", "#c44f4f" if t > 0 else "#2f74c9", min(abs(t), 1.0))
        cells.append(f'<div class="lqv-cell" style="--bg:{bg};--i:{i}" title="{i + 1}번: 평균 대비 {v:.0f}">'
                     f'<b>{i + 1}</b><small>{v:.0f}</small></div>')
    return ('<div class="lqv-grid">' + "".join(cells) + '</div>'
            '<div class="lqv-legend"><span>🟦 사람들이 덜 고르는 번호</span><span>100 = 평균</span>'
            '<span>사람들이 많이 고르는 번호 🟥</span></div>')


STAT_STRIP = """
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: transparent; font-family: __FONT__; }
  .strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
  .tile { background: linear-gradient(160deg, rgba(38,38,36,.95), rgba(22,22,21,.95)); border: 1px solid rgba(255,255,255,.10);
    border-radius: 14px; padding: 14px 16px; opacity: 0; transform: translateY(12px);
    animation: rise .5s cubic-bezier(.2,.8,.2,1) forwards; }
  .tile:nth-child(2) { animation-delay: .07s; } .tile:nth-child(3) { animation-delay: .14s; } .tile:nth-child(4) { animation-delay: .21s; }
  .label { color: #c3c2b7; font-size: 13px; }
  .value { color: #fff; font-size: 27px; font-weight: 800; margin-top: 4px; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .value small { font-size: 15px; font-weight: 600; color: #c3c2b7; margin-left: 2px; }
  .note { color: #898781; font-size: 12px; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .gold .value { color: #fab219; }
  @keyframes rise { to { opacity: 1; transform: none; } }
  @media (max-width: 640px) { .strip { grid-template-columns: repeat(2, minmax(0, 1fr)); } .value { font-size: 22px; } }
  @media (prefers-reduced-motion: reduce) { .tile { animation: none; opacity: 1; transform: none; } }
</style>
<div class="strip" id="strip"></div>
<script>
(function () {
  const TILES = __DATA__;
  const strip = document.getElementById('strip');
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fmt = (v, d) => v.toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d });
  TILES.forEach((t) => {
    const el = document.createElement('div');
    el.className = 'tile' + (t.gold ? ' gold' : '');
    const label = document.createElement('div'); label.className = 'label'; label.textContent = t.label;
    const value = document.createElement('div'); value.className = 'value';
    const num = document.createElement('span'); const unit = document.createElement('small'); unit.textContent = t.unit;
    value.append(num, unit);
    const note = document.createElement('div'); note.className = 'note'; note.textContent = t.note || '';
    el.append(label, value, note); strip.appendChild(el);
    const d = t.decimals || 0;
    if (reduce) { num.textContent = fmt(t.value, d); return; }
    const start = performance.now(), dur = 1100;
    (function tick(now) {
      const p = Math.min((now - start) / dur, 1), e = 1 - Math.pow(1 - p, 3);
      num.textContent = fmt(t.value * e, d);
      if (p < 1) requestAnimationFrame(tick); else num.textContent = fmt(t.value, d);
    })(start);
  });
})();
</script>
"""


def stat_strip(tiles: list[dict]) -> str:
    """Count-up tiles. Each tile: {label, value, unit, decimals?, note?, gold?}."""
    return STAT_STRIP.replace("__FONT__", FONT_STACK).replace("__DATA__", json.dumps(tiles, ensure_ascii=False))


def _tier_text(my_numbers, drawn_main, bonus) -> tuple[str, int, bool]:
    match_count = len(set(my_numbers) & set(drawn_main))
    has_bonus = bonus in my_numbers
    tier_map = {
        6: "\U0001F947 1등 (6개 일치)",
        5: ("\U0001F948 2등 (5개 + 보너스)" if has_bonus else "\U0001F949 3등 (5개 일치)"),
        4: "4등 (4개 일치)",
        3: "5등 (3개 일치)",
    }
    tier = tier_map.get(match_count, "낙첨 (등외)")
    text = f"{tier} — {match_count}개 일치" + (" + 보너스" if has_bonus and match_count == 5 else "")
    return text, match_count, has_bonus


DRAW_MACHINE = """
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: transparent; font-family: __FONT__; color: #c3c2b7; }
  .wrap { position: relative; display: flex; flex-direction: column; align-items: center; padding: 6px 0 0; overflow: hidden; }
  .stage { position: relative; width: 320px; height: 356px; }
  #drum { position: absolute; left: 0; top: 36px; width: 320px; height: 320px; border-radius: 50%; }
  .glass { position: absolute; left: 0; top: 36px; width: 320px; height: 320px; border-radius: 50%; pointer-events: none;
    border: 9px solid #4a5568;
    background: radial-gradient(circle at 30% 24%, rgba(255,255,255,.20), transparent 34%),
                radial-gradient(circle at 70% 82%, rgba(120,160,220,.10), transparent 50%);
    box-shadow: 0 14px 34px rgba(0,0,0,.65), inset 0 0 44px rgba(120,160,220,.22), 0 0 0 1px rgba(255,255,255,.08); }
  .chute { position: absolute; left: 50%; top: 0; width: 46px; height: 48px; margin-left: -23px; border-radius: 12px 12px 4px 4px;
    background: linear-gradient(90deg, #2c333d, #5b6472 45%, #2c333d); box-shadow: inset 0 0 8px rgba(0,0,0,.6); }
  .chute::after { content: ""; position: absolute; left: 8px; right: 8px; top: 6px; height: 4px; border-radius: 2px;
    background: #69c8f2; opacity: .25; transition: opacity .2s; }
  .chute.on::after { opacity: 1; box-shadow: 0 0 12px #69c8f2; }
  .stand { width: 16px; height: 26px; background: linear-gradient(#5b6472, #2c333d); margin-top: -2px; }
  .base { width: 170px; height: 14px; border-radius: 8px; background: linear-gradient(#4a5568, #232830); box-shadow: 0 5px 12px rgba(0,0,0,.55); }
  .label { margin-top: 10px; font-weight: 800; letter-spacing: 3px; font-size: 13px; }
  .row { display: flex; align-items: center; justify-content: center; gap: 8px; flex-wrap: wrap; }
  .trays { margin-top: 18px; }
  .slot { width: 44px; height: 44px; border-radius: 50%; border: 2px dashed #3a3f4a; }
  .ball { width: 44px; height: 44px; border-radius: 50%; color: #fff; font-weight: 800; font-size: 17px;
    display: flex; align-items: center; justify-content: center; text-shadow: 0 1px 2px rgba(0,0,0,.5);
    background: radial-gradient(circle at 32% 26%, rgba(255,255,255,.85) 0 7%, rgba(255,255,255,.22) 22%, transparent 42%),
                radial-gradient(circle at 70% 80%, rgba(0,0,0,.34), transparent 58%), var(--c);
    box-shadow: 0 5px 10px rgba(0,0,0,.5), inset 0 -3px 6px rgba(0,0,0,.22); }
  .ball.in { animation: drop .62s cubic-bezier(.3,1.35,.6,1) both; }
  .ball.hit { box-shadow: 0 0 0 3px #fab219, 0 0 18px rgba(250,178,25,.7), 0 5px 10px rgba(0,0,0,.5); }
  .ball.hit.in { animation: drop .62s cubic-bezier(.3,1.35,.6,1) both, ring 1.1s ease-out .62s 2; }
  .plus { font-size: 20px; font-weight: 700; color: #898781; }
  .mine { margin-top: 16px; }
  .mine .cap { font-size: 12px; color: #898781; margin-right: 6px; }
  .chip { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 700; color: #c3c2b7; border: 1px solid #3a3f4a; background: #1a1a19;
    transition: transform .3s cubic-bezier(.3,1.5,.6,1), background .3s, color .3s, border-color .3s; }
  .chip.hit { background: #fab219; color: #1a1300; border-color: #fab219; transform: scale(1.18); }
  .chip.bonus { background: #69c8f2; color: #06202c; border-color: #69c8f2; transform: scale(1.12); }
  .result { margin-top: 16px; padding: 13px 26px; border-radius: 12px; background: #1a1a19; border: 1px solid rgba(255,255,255,.10);
    font-size: 17px; font-weight: 700; text-align: center; opacity: 0; transform: translateY(10px) scale(.96);
    transition: opacity .45s ease-out, transform .45s cubic-bezier(.3,1.4,.6,1); }
  .result.show { opacity: 1; transform: none; }
  .result.won { background: linear-gradient(135deg, #3a2f0a, #4a3a08); color: #fab219; border-color: rgba(250,178,25,.4);
    box-shadow: 0 6px 22px rgba(250,178,25,.28); }
  .again { margin-top: 12px; background: transparent; color: #c3c2b7; border: 1px solid rgba(255,255,255,.18); border-radius: 10px;
    padding: 7px 16px; font-size: 13px; cursor: pointer; opacity: 0; pointer-events: none;
    transition: opacity .3s, transform .12s, border-color .2s; font-family: inherit; }
  .again.show { opacity: 1; pointer-events: auto; }
  .again:hover { border-color: #69c8f2; color: #fff; } .again:active { transform: scale(.96); }
  #confetti { position: absolute; left: 0; top: 0; width: 100%; height: 100%; pointer-events: none; }
  @keyframes drop { 0% { transform: translateY(-90px) scale(.3); opacity: 0; } 60% { transform: translateY(5px) scale(1.1); opacity: 1; } 100% { transform: none; } }
  @keyframes ring { 0% { box-shadow: 0 0 0 3px #fab219, 0 0 0 0 rgba(250,178,25,.6); } 100% { box-shadow: 0 0 0 3px #fab219, 0 0 0 16px rgba(250,178,25,0); } }
  @media (max-width: 420px) { .slot, .ball { width: 36px; height: 36px; font-size: 14px; } .row { gap: 5px; } .plus { font-size: 16px; } }
  @media (prefers-reduced-motion: reduce) { .ball.in, .ball.hit.in { animation: none; } .chip, .result { transition: none; } }
</style>
<div class="wrap" id="root">
  <div class="stage">
    <div class="chute" id="chute"></div>
    <canvas id="drum" width="320" height="320"></canvas>
    <div class="glass"></div>
  </div>
  <div class="stand"></div><div class="base"></div>
  <div class="label">LOTTO 6/45</div>
  <div class="row trays" id="trays" aria-live="polite"></div>
  <div class="row mine" id="mine"><span class="cap">내 번호</span></div>
  <div class="result" id="result" role="status"></div>
  <button class="again" id="again" type="button">↻ 추첨 장면 다시 보기</button>
  <canvas id="confetti"></canvas>
</div>
<script>
(function () {
  const DATA = __DATA__;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const cv = document.getElementById('drum'), ctx = cv.getContext('2d');
  const dpr = Math.min(window.devicePixelRatio || 1, 2), SIZE = 320;
  cv.width = SIZE * dpr; cv.height = SIZE * dpr; ctx.scale(dpr, dpr);
  const C = SIZE / 2, RAD = C - 12, BR = 11.5;
  const trays = document.getElementById('trays'), mine = document.getElementById('mine');
  const result = document.getElementById('result'), again = document.getElementById('again');
  const chute = document.getElementById('chute'), root = document.getElementById('root');
  const order = DATA.drawnMain.concat([DATA.bonus]);
  let balls = [], blower = 0, target = null, raf = 0, timers = [], chips = {};

  function later(fn, ms) { timers.push(setTimeout(fn, ms)); }

  function build() {
    trays.textContent = '';
    for (let i = 0; i < 7; i++) {
      if (i === 6) { const p = document.createElement('div'); p.className = 'plus'; p.textContent = '+'; trays.appendChild(p); }
      const s = document.createElement('div'); s.className = 'slot'; s.dataset.i = i; trays.appendChild(s);
    }
    mine.querySelectorAll('.chip').forEach((c) => c.remove()); chips = {};
    DATA.myNumbers.forEach((n) => {
      const c = document.createElement('div'); c.className = 'chip'; c.textContent = n; mine.appendChild(c); chips[n] = c;
    });
    result.className = 'result'; result.textContent = ''; again.classList.remove('show');
    balls = [];
    for (let n = 1; n <= 45; n++) {
      const a = Math.random() * Math.PI * 2, r = Math.sqrt(Math.random()) * (RAD - BR - 4);
      balls.push({ n: n, x: C + r * Math.cos(a), y: C + r * Math.sin(a) * 0.6 + 40, vx: 0, vy: 0, rot: Math.random() * 6.28, out: false });
    }
  }

  function step() {
    const G = 0.32;
    for (const b of balls) {
      if (b.out) continue;
      b.vy += G;
      if (blower > 0) {                      // air jets from the bottom keep the balls tumbling
        const depth = (b.y - C) / RAD;
        if (depth > 0.3 && Math.random() < 0.07 * blower) {      // a puff throws a ball back up
          b.vy = -(5.5 + Math.random() * 5.5); b.vx += (Math.random() - 0.5) * 7;
        }
        b.vx += -(b.y - C) / RAD * 0.05 * blower; b.vy += (b.x - C) / RAD * 0.05 * blower;   // slow swirl
      }
      if (b === target) {                    // the picked ball is pulled up into the chute
        const dx = C - b.x, dy = (C - RAD + 4) - b.y, d = Math.hypot(dx, dy) || 1;
        b.vx += dx / d * 1.25; b.vy += dy / d * 1.25 - G; b.vx *= 0.93; b.vy *= 0.93;
      }
      b.vx *= 0.992; b.vy *= 0.992;
      b.x += b.vx; b.y += b.vy; b.rot += b.vx * 0.03;
      const dx = b.x - C, dy = b.y - C, d = Math.hypot(dx, dy), lim = RAD - BR;
      if (d > lim) {
        const nx = dx / d, ny = dy / d, vn = b.vx * nx + b.vy * ny;
        b.x = C + nx * lim; b.y = C + ny * lim;
        if (vn > 0) { b.vx -= 1.72 * vn * nx; b.vy -= 1.72 * vn * ny; }
      }
    }
    for (let i = 0; i < balls.length; i++) {
      const a = balls[i]; if (a.out) continue;
      for (let j = i + 1; j < balls.length; j++) {
        const b = balls[j]; if (b.out) continue;
        const dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy, min = BR * 2;
        if (d2 < min * min && d2 > 0.0001) {
          const d = Math.sqrt(d2), nx = dx / d, ny = dy / d, push = (min - d) / 2;
          a.x -= nx * push; a.y -= ny * push; b.x += nx * push; b.y += ny * push;
          const rel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
          if (rel < 0) { const imp = rel * 0.9; a.vx += imp * nx; a.vy += imp * ny; b.vx -= imp * nx; b.vy -= imp * ny; }
        }
      }
    }
  }

  function draw() {
    ctx.clearRect(0, 0, SIZE, SIZE);
    const bg = ctx.createRadialGradient(C - 40, C - 50, 20, C, C, RAD + 8);
    bg.addColorStop(0, 'rgba(70,95,140,.55)'); bg.addColorStop(1, 'rgba(14,18,28,.92)');
    ctx.fillStyle = bg; ctx.beginPath(); ctx.arc(C, C, RAD + 4, 0, 6.2832); ctx.fill();
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.font = '800 10.5px sans-serif';
    for (const b of balls) {
      if (b.out) continue;
      const g = ctx.createRadialGradient(b.x - 3.5, b.y - 4, 1, b.x, b.y, BR);
      g.addColorStop(0, '#ffffff'); g.addColorStop(0.28, DATA.colors[b.n]); g.addColorStop(1, 'rgba(0,0,0,.55)');
      ctx.fillStyle = DATA.colors[b.n]; ctx.beginPath(); ctx.arc(b.x, b.y, BR, 0, 6.2832); ctx.fill();
      ctx.globalAlpha = 0.55; ctx.fillStyle = g; ctx.fill(); ctx.globalAlpha = 1;
      if (b === target) { ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2; ctx.stroke(); }
      ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.rot);
      ctx.fillStyle = 'rgba(0,0,0,.35)'; ctx.fillText(b.n, 0.6, 1.1); ctx.fillStyle = '#fff'; ctx.fillText(b.n, 0, 0.4);
      ctx.restore();
    }
  }

  function loop() { step(); step(); draw(); raf = requestAnimationFrame(loop); }

  function land(i) {
    const n = order[i], slot = trays.querySelector('.slot[data-i="' + i + '"]');
    const isBonus = i === 6, mineHas = DATA.myNumbers.indexOf(n) >= 0;
    const el = document.createElement('div');
    el.className = 'ball in' + (mineHas && !isBonus ? ' hit' : '');
    el.style.setProperty('--c', DATA.colors[n]); el.textContent = n;
    if (slot) slot.replaceWith(el);
    if (mineHas && chips[n]) chips[n].classList.add(isBonus ? 'bonus' : 'hit');
  }

  function pick(i, done) {
    target = balls.find((b) => b.n === order[i]);
    chute.classList.add('on');
    const started = performance.now();
    (function wait() {
      const b = target, near = b && Math.hypot(b.x - C, b.y - (C - RAD + 4)) < 26;
      if (near || performance.now() - started > 1500) {
        if (b) b.out = true; target = null; chute.classList.remove('on'); land(i); done();
      } else { timers.push(setTimeout(wait, 30)); }
    })();
  }

  function finish() {
    blower = 0;
    result.textContent = DATA.tierText;
    result.classList.add('show'); if (DATA.won) { result.classList.add('won'); confetti(); }
    again.classList.add('show');
  }

  function run() {
    timers.forEach(clearTimeout); timers = []; cancelAnimationFrame(raf);
    build();
    if (reduce) {                            // no motion: show the settled drum and the result at once
      order.forEach((n, i) => { balls.find((b) => b.n === n).out = true; land(i); });
      for (let k = 0; k < 400; k++) step();
      draw(); finish(); return;
    }
    blower = 1; loop();
    let i = 0;
    const next = () => {
      if (i >= order.length) { later(finish, 700); return; }
      later(() => pick(i++, next), i === 0 ? 2300 : (i === 6 ? 1100 : 620));
    };
    next();
  }

  function confetti() {
    if (reduce) return;
    const cf = document.getElementById('confetti'), c2 = cf.getContext('2d');
    const w = root.clientWidth, h = root.clientHeight; cf.width = w * dpr; cf.height = h * dpr; c2.setTransform(dpr, 0, 0, dpr, 0, 0);
    const colors = ['#fab219', '#69c8f2', '#ff7272', '#b0d840', '#ffffff'];
    const n = 60 + DATA.matchCount * 30, parts = [];
    for (let k = 0; k < n; k++) parts.push({ x: w / 2 + (Math.random() - .5) * 120, y: h * .55, vx: (Math.random() - .5) * 11,
      vy: -6 - Math.random() * 9, r: Math.random() * 6.28, vr: (Math.random() - .5) * .4, s: 5 + Math.random() * 6, c: colors[k % 5], life: 1 });
    (function tick() {
      c2.clearRect(0, 0, w, h); let alive = false;
      for (const p of parts) {
        p.vy += .28; p.vx *= .99; p.x += p.vx; p.y += p.vy; p.r += p.vr; if (p.y > h * .7) p.life -= .02;
        if (p.life <= 0) continue; alive = true;
        c2.save(); c2.globalAlpha = Math.max(p.life, 0); c2.translate(p.x, p.y); c2.rotate(p.r);
        c2.fillStyle = p.c; c2.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2); c2.restore();
      }
      if (alive) requestAnimationFrame(tick); else c2.clearRect(0, 0, w, h);
    })();
  }

  again.addEventListener('click', run);
  run();
})();
</script>
"""


def render_draw_machine(my_numbers: list[int], drawn_main: list[int], bonus: int) -> str:
    """Canvas draw machine: 45 balls tumble in a glass drum (real collisions), each winning
    ball is pulled up the chute and drops into the tray, matched numbers light up, and a win
    throws confetti. The result is decided in Python; this only plays it back."""
    text, match_count, _ = _tier_text(my_numbers, drawn_main, bonus)
    data = {
        "drawnMain": [int(n) for n in drawn_main],
        "bonus": int(bonus),
        "myNumbers": [int(n) for n in my_numbers],
        "won": match_count >= 3,
        "matchCount": match_count,
        "tierText": text,
        "colors": {str(n): ball_color(n) for n in range(1, 46)},
    }
    return DRAW_MACHINE.replace("__FONT__", FONT_STACK).replace("__DATA__", json.dumps(data, ensure_ascii=False))

