"""LOTTO 6/45 QUANT V3 -- Streamlit dashboard.

Run with:  streamlit run lotto_quant_v3/dashboard/app.py
(from the project root, so the lotto_quant_v3 package resolves)
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# Make the repo root importable regardless of streamlit's script-dir sys.path quirk.
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lotto_quant_v3.backtest import walkforward
from lotto_quant_v3.data import db, news_search
from lotto_quant_v3.optimization import optimizer
from lotto_quant_v3.portfolio import generator, probability
from lotto_quant_v3.probability import engine as prob_engine
from lotto_quant_v3.simulation import monte_carlo
from lotto_quant_v3.statistics import analysis, randomness_tests, significance

st.set_page_config(page_title="LOTTO 6/45 QUANT V3", page_icon="🎱", layout="wide")

BALL_COLORS = {
    range(1, 11): "#fbc400",
    range(11, 21): "#69c8f2",
    range(21, 31): "#ff7272",
    range(31, 41): "#aaaaaa",
    range(41, 46): "#b0d840",
}


def ball_color(n: int) -> str:
    for rng, color in BALL_COLORS.items():
        if n in rng:
            return color
    return "#333333"


def render_balls(numbers, bonus: int | None = None, size: int = 46) -> str:
    def ball_html(n, extra_border=""):
        return (
            f'<div style="display:inline-flex;align-items:center;justify-content:center;'
            f'width:{size}px;height:{size}px;border-radius:50%;background:{ball_color(n)};'
            f'color:white;font-weight:700;font-size:{int(size*0.4)}px;margin:4px;'
            f'box-shadow:0 2px 4px rgba(0,0,0,.3);{extra_border}">{n}</div>'
        )
    html = "".join(ball_html(n) for n in numbers)
    if bonus is not None:
        html += (
            '<span style="font-size:22px;margin:0 6px;color:#888;">+</span>'
            + ball_html(bonus, extra_border="border:3px solid #222;")
        )
    return html


def _drum_ball_positions(n: int = 45, radius: float = 118, cx: float = 145, cy: float = 145):
    """Sunflower (golden-angle) point distribution so 45 balls pack a circle
    evenly with no overlap clustering, mirroring the physical draw machine."""
    golden_angle = math.radians(137.508)
    pts = []
    for i in range(n):
        r = radius * math.sqrt((i + 0.5) / n)
        theta = i * golden_angle
        pts.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
    return pts


def render_draw_machine(my_numbers: list[int], drawn_main: list[int], bonus: int) -> str:
    """Self-contained HTML/CSS/JS draw-machine animation: a spinning glass
    drum full of the 45 numbered balls, then a mechanical one-by-one eject
    into a tray, then the result -- all timed client-side (independent of
    Streamlit's rerun cycle) so it plays smoothly instead of the old
    blocking time.sleep()-per-frame approach."""
    ball_d = 22
    drum_balls_html = "".join(
        f'<div class="drum-ball" style="left:{x - ball_d / 2:.1f}px;top:{y - ball_d / 2:.1f}px;'
        f'width:{ball_d}px;height:{ball_d}px;background:{ball_color(n)};'
        f'animation-duration:{1.1 + (n % 5) * 0.13:.2f}s;animation-delay:{(n % 7) * 0.09:.2f}s;">{n}</div>'
        for n, (x, y) in zip(range(1, 46), _drum_ball_positions())
    )

    match_set = set(my_numbers) & set(drawn_main)
    has_bonus = bonus in my_numbers
    match_count = len(match_set)
    tier_map = {
        6: "\U0001F947 1등 (6개 일치)",
        5: ("\U0001F948 2등 (5개 + 보너스)" if has_bonus else "\U0001F949 3등 (5개 일치)"),
        4: "4등 (4개 일치)",
        3: "5등 (3개 일치)",
    }
    tier = tier_map.get(match_count, "낙첨 (등외)")

    data = {
        "drawnMain": drawn_main,
        "bonus": bonus,
        "myNumbers": my_numbers,
        "won": match_count >= 3,
        "matchCount": match_count,
        "tierText": f"{tier} — {match_count}개 일치" + (" + 보너스" if has_bonus and match_count == 5 else ""),
        "colors": {str(n): ball_color(n) for n in range(1, 46)},
    }
    data_json = json.dumps(data, ensure_ascii=False)

    return f"""
<style>
  * {{ box-sizing: border-box; }}
  .machine-wrap {{ font-family: -apple-system, "Segoe UI", sans-serif; display:flex; flex-direction:column;
    align-items:center; padding:10px 0 0; }}
  .drum {{ position:relative; width:290px; height:290px; border-radius:50%;
    background: radial-gradient(circle at 32% 28%, rgba(255,255,255,.95), rgba(200,228,255,.35) 42%, rgba(140,170,210,.28) 100%);
    border: 9px solid #8a94a3; box-shadow: 0 8px 22px rgba(0,0,0,.35), inset 0 0 30px rgba(255,255,255,.5);
    overflow: hidden; transition: transform 2.1s cubic-bezier(.36,.07,.19,.97); }}
  .drum.spinning {{ transform: rotate(1080deg); }}
  .drum-ball {{ position:absolute; border-radius:50%; color:#fff; font-weight:700;
    font-size:10px; display:flex; align-items:center; justify-content:center;
    box-shadow: 0 1px 2px rgba(0,0,0,.4), inset -2px -2px 3px rgba(0,0,0,.25), inset 2px 2px 3px rgba(255,255,255,.5);
    animation-name: jitter; animation-iteration-count: infinite; animation-timing-function: ease-in-out; }}
  @keyframes jitter {{ 0%,100% {{ transform: translate(0,0); }} 50% {{ transform: translate(1.5px,-2px); }} }}
  .stand {{ width:14px; height:34px; background: linear-gradient(#9aa4b2,#6b7280); margin-top:-4px; }}
  .base {{ width:150px; height:14px; border-radius:8px; background: linear-gradient(#7b8593,#5b6472);
    box-shadow: 0 4px 8px rgba(0,0,0,.3); margin-top:-2px; }}
  .machine-label {{ margin-top:10px; font-weight:800; letter-spacing:2px; color:#345; font-size:13px; }}
  .trays {{ display:flex; align-items:center; gap:14px; margin-top:22px; flex-wrap:wrap; justify-content:center; }}
  .tray-main, .tray-bonus {{ display:flex; gap:8px; }}
  .tray-slot {{ width:40px; height:40px; border-radius:50%; border:2px dashed #c3ccd6; }}
  .tray-ball {{ width:40px; height:40px; border-radius:50%; color:#fff; font-weight:700; font-size:15px;
    display:flex; align-items:center; justify-content:center; box-shadow:0 3px 6px rgba(0,0,0,.35);
    animation: pop .5s cubic-bezier(.34,1.56,.64,1); }}
  .tray-ball.match {{ box-shadow: 0 0 0 3px #ffd700, 0 3px 8px rgba(0,0,0,.4); }}
  @keyframes pop {{ 0% {{ transform: translateY(-70px) scale(.3); opacity:0; }}
    60% {{ transform: translateY(6px) scale(1.12); opacity:1; }} 100% {{ transform: translateY(0) scale(1); }} }}
  .plus-sep {{ font-size:20px; color:#889; font-weight:700; }}
  .result-box {{ margin-top:22px; padding:14px 26px; border-radius:12px; background:#f1f3f6; color:#334;
    font-size:17px; font-weight:700; opacity:0; transform:translateY(8px); transition: all .5s ease; text-align:center; }}
  .result-box.show {{ opacity:1; transform:translateY(0); }}
  .result-box.won {{ background: linear-gradient(135deg,#fff6d8,#ffe9a8); color:#8a6400;
    box-shadow: 0 4px 14px rgba(255,200,0,.35); }}
  .confetti {{ position:absolute; font-size:18px; animation: fall 1.6s ease-in forwards; }}
  @keyframes fall {{ 0% {{ transform: translateY(-10px) rotate(0deg); opacity:1; }}
    100% {{ transform: translateY(160px) rotate(360deg); opacity:0; }} }}
</style>
<div class="machine-wrap" id="lm-root" style="position:relative;">
  <div class="drum" id="lm-drum">{drum_balls_html}</div>
  <div class="stand"></div>
  <div class="base"></div>
  <div class="machine-label">LOTTO 6/45</div>
  <div class="trays">
    <div class="tray-main" id="lm-tray-main">
      <div class="tray-slot"></div><div class="tray-slot"></div><div class="tray-slot"></div>
      <div class="tray-slot"></div><div class="tray-slot"></div><div class="tray-slot"></div>
    </div>
    <div class="plus-sep">+</div>
    <div class="tray-bonus" id="lm-tray-bonus"><div class="tray-slot"></div></div>
  </div>
  <div class="result-box" id="lm-result"><span id="lm-result-text"></span></div>
</div>
<script>
(function() {{
  const DATA = {data_json};
  const root = document.getElementById('lm-root');
  const drum = document.getElementById('lm-drum');
  const trayMain = document.getElementById('lm-tray-main');
  const trayBonus = document.getElementById('lm-tray-bonus');
  const resultBox = document.getElementById('lm-result');
  const resultText = document.getElementById('lm-result-text');
  const mainSlots = trayMain.querySelectorAll('.tray-slot');
  const bonusSlot = trayBonus.querySelector('.tray-slot');

  function makeBall(n) {{
    const d = document.createElement('div');
    d.className = 'tray-ball' + (DATA.myNumbers.includes(n) ? ' match' : '');
    d.style.background = DATA.colors[String(n)];
    d.textContent = n;
    return d;
  }}

  setTimeout(() => drum.classList.add('spinning'), 60);

  const spinDuration = 2150, step = 650;
  let t = spinDuration + 250;
  DATA.drawnMain.forEach((n, i) => {{
    setTimeout(() => {{ mainSlots[i].replaceWith(makeBall(n)); }}, t + i * step);
  }});

  const bonusDelay = t + DATA.drawnMain.length * step + 350;
  setTimeout(() => {{ bonusSlot.replaceWith(makeBall(DATA.bonus)); }}, bonusDelay);

  const resultDelay = bonusDelay + 900;
  setTimeout(() => {{
    resultText.textContent = DATA.tierText;
    resultBox.classList.add('show');
    if (DATA.won) {{
      resultBox.classList.add('won');
      const emojis = ['\\ud83c\\udf89','\\u2728','\\ud83c\\udf8a','\\ud83d\\udcb0'];
      for (let i = 0; i < 14; i++) {{
        const c = document.createElement('div');
        c.className = 'confetti';
        c.textContent = emojis[i % emojis.length];
        c.style.left = (10 + Math.random() * 260) + 'px';
        c.style.top = '0px';
        c.style.animationDelay = (Math.random() * .4) + 's';
        root.appendChild(c);
      }}
    }}
  }}, resultDelay);
}})();
</script>
"""


@st.cache_data(ttl=3600)
def load_history_df():
    draws = db.get_all_draws()
    if not draws:
        return None
    return analysis.draws_to_frame(draws)


def page_overview():
    st.title("🎱 LOTTO 6/45 QUANT V3")
    df = load_history_df()
    if df is None:
        st.warning("DB에 데이터가 없습니다. 사이드바에서 '데이터 갱신'을 먼저 실행하세요.")
        return
    latest = df.iloc[-1]
    c1, c2, c3 = st.columns(3)
    c1.metric("최신 회차", int(latest["round"]))
    c2.metric("추첨일", latest["date"])
    c3.metric("DB 보유 회차 수", len(df))
    st.markdown("**최신 당첨번호**", unsafe_allow_html=True)
    st.markdown(render_balls(latest["numbers"], latest["bonus"]), unsafe_allow_html=True)
    st.caption("데이터 출처: 사용자 제공 1~1236회 이력 (엑셀, 검증됨) + 이후 회차는 "
               "Google 뉴스 검색으로 자동 수집 (언론사 2곳 이상 일치해야 저장, 사이드바 "
               "'새 회차 확인' 버튼). 동행복권 공식 API(common.do?method=getLottoNumber)는 "
               "2026-01 사이트 개편 이후 접근 불가함을 확인함 (봇 우회 시도 없음).")


def page_statistics():
    st.title("📊 통계 분석")
    df = load_history_df()
    if df is None:
        st.warning("데이터가 없습니다.")
        return
    freq = analysis.number_frequency(df)
    fig = go.Figure(go.Bar(x=freq.index, y=freq.values, marker_color=[ball_color(n) for n in freq.index]))
    fig.update_layout(title="번호별 출현 빈도", xaxis_title="번호", yaxis_title="출현 횟수")
    st.plotly_chart(fig, width="stretch")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("최다 출현 (Hot)")
        st.dataframe(freq.sort_values(ascending=False).head(10).rename("횟수"))
    with col2:
        st.subheader("최소 출현 (Cold)")
        st.dataframe(freq.sort_values(ascending=True).head(10).rename("횟수"))

    gaps = analysis.gap_since_last_seen(df)
    st.subheader("미출현 회차 수 (오래 안 나온 순)")
    st.dataframe(gaps.dropna().sort_values(ascending=False).head(10).rename("미출현 회차"))

    sums = analysis.sum_distribution(df)
    fig2 = go.Figure(go.Histogram(x=sums, nbinsx=30))
    fig2.update_layout(title=f"번호 합계 분포 (평균={sums.mean():.1f}, 표준편차={sums.std():.1f})")
    st.plotly_chart(fig2, width="stretch")


def page_probability():
    st.title("🎯 확률 엔진")
    summary = prob_engine.summarize()
    st.metric("C(45,6) 전체 조합 수", f"{summary['total_combinations']:,}")
    rows = []
    for tier, info in summary["tiers"].items():
        rows.append({
            "등수": tier, "조건": info["label"], "경우의 수": f"{info['ways']:,}",
            "확률": f"{info['probability']:.8f}",
            "당첨 확률": f"1 / {info['odds_1_in']:,.1f}",
        })
    st.table(pd.DataFrame(rows))


def page_randomness():
    st.title("🔬 정밀 통계 검증")
    st.caption(
        "예측 도구가 아닙니다 -- '이 데이터가 정말 i.i.d. 균등분포인가'를 엄밀하게 "
        "검정합니다. 모든 검정이 귀무가설을 기각하지 못하는 것이 정상이자 기대되는 결과입니다."
    )
    df = load_history_df()
    if df is None:
        st.warning("데이터가 없습니다.")
        return

    if st.button("🔬 정밀 검정 실행"):
        with st.spinner("카이제곱 · 런 검정 · 자기상관 · 엔트로피 분석 중..."):
            result = randomness_tests.summarize_randomness(df)

        n_reject = result["tests_rejecting_null_of_3"]
        if n_reject == 0:
            st.success(result["overall_conclusion"])
        else:
            st.warning(result["overall_conclusion"])

        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("1. 카이제곱 균등성 검정")
            chi2 = result["chi_square_uniformity"]
            st.metric("p-value", f"{chi2['p_value']:.4f}")
            st.write(f"χ² = {chi2['statistic']:.2f}, dof = {chi2['dof']}")
            st.caption(chi2["interpretation"])

            st.subheader("3. 자기상관 검정 (lag 1-3)")
            for lag_name, lag in result["autocorrelation"]["lags"].items():
                st.write(f"**{lag_name}**: r = {lag['correlation']:.4f}, p = {lag['p_value']:.4f}")
            st.caption(result["autocorrelation"]["interpretation"])

        with c2:
            st.subheader("2. Wald-Wolfowitz 런 검정")
            runs = result["runs_test"]
            st.metric("p-value", f"{runs['p_value']:.4f}")
            st.write(f"관측된 런: {runs['observed_runs']} (기대값: {runs['expected_runs']:.1f})")
            st.caption(runs["interpretation"])

            st.subheader("4. 섀넌 엔트로피")
            ent = result["entropy"]
            st.metric("엔트로피 비율 (1.0=완전균등)", f"{ent['ratio_to_max']:.4f}")
            st.write(f"H = {ent['entropy_bits']:.4f} bits (최대 {ent['max_entropy_bits']:.4f} bits)")
            st.caption(ent["interpretation"])

        st.divider()
        st.caption(
            "다중검정 보정 참고: 검정 4개를 α=0.05로 각각 돌리면, 데이터가 진짜 무작위여도 "
            "우연히 하나 이상 기각될 확률은 1-(0.95)^4 ≈ 18.5%입니다. 단일 유의 결과만으로 "
            "비무작위성을 결론짓지 않는 이유입니다."
        )


def page_portfolio():
    st.title("💼 포트폴리오 생성 & 정확 확률")
    df = load_history_df()
    mode = st.radio("생성 방식", ["균등 랜덤 (baseline)", "빈도 가중 (V3)", "분산 최적화 (V3 optimizer)"])

    use_fixed_seed = st.checkbox("시드 고정 (재현용 -- 끄면 매번 새로운 무작위 번호)", value=False)
    seed = None
    if use_fixed_seed:
        seed = int(st.number_input("시드 값", value=0, step=1))

    weights = None
    if mode != "균등 랜덤 (baseline)" and df is not None:
        weights = (analysis.number_frequency(df).values + 1).astype(float)

    if st.button("5게임 생성"):
        if mode == "분산 최적화 (V3 optimizer)":
            tickets = optimizer.optimize_portfolio(weights=weights, seed=seed)
        else:
            tickets = generator.generate_portfolio(weights=weights, seed=seed)
        st.session_state["portfolio"] = tickets

    tickets = st.session_state.get("portfolio")
    if tickets:
        for i, t in enumerate(tickets, 1):
            st.markdown(f"**게임 {i}**", unsafe_allow_html=True)
            st.markdown(render_balls(t, size=36), unsafe_allow_html=True)

        if st.button("이 포트폴리오의 정확 당첨 확률 계산 (전수조사, 약 5~10초)"):
            with st.spinner("C(45,6) = 8,145,060개 조합 전수 계산 중..."):
                result = probability.exact_portfolio_distribution(tickets)
            st.success(f"1등(6개 일치) 확률: {result['jackpot_ways']} / {result['total_draws']:,} "
                       f"= {result['jackpot_probability']:.10f}")
            st.json(result["exact_probability_at_least"])


def page_simulation():
    st.title("🔁 Monte Carlo 시뮬레이션")
    tickets = st.session_state.get("portfolio")
    if not tickets:
        st.info("먼저 '포트폴리오' 탭에서 5게임을 생성하세요.")
        return
    n_draws = st.select_slider("시뮬레이션 추첨 횟수", options=[100_000, 300_000, 1_000_000], value=100_000)
    if st.button("시뮬레이션 실행"):
        with st.spinner(f"{n_draws:,}회 추첨 시뮬레이션 중..."):
            mc = monte_carlo.simulate_portfolio(tickets, n_draws=n_draws, seed=1)
        st.json(mc["probability_at_least"])
        fig = go.Figure(go.Bar(x=list(mc["counts"].keys()), y=list(mc["counts"].values())))
        fig.update_layout(title="최고 적중 개수 분포", xaxis_title="일치 개수", yaxis_title="횟수")
        st.plotly_chart(fig, width="stretch")


def page_noise_check():
    st.title("⚖️ 조합 비교 (신호 vs 노이즈)")
    st.caption(
        "여러 조합을 대량 시뮬레이션으로 직접 경쟁시켜서, '가장 잘 맞는 조합'이 "
        "실제로 존재하는지 이 자리에서 검증합니다. 로또가 공정하다면 모든 조합의 "
        "이론적 기대 적중 개수는 정확히 같아야 하고 (6×6/45 = 0.8개), 관측되는 "
        "차이는 표본오차(노이즈)로 전부 설명되어야 합니다."
    )

    n_draws = st.select_slider(
        "시뮬레이션 추첨 횟수", options=[500_000, 1_000_000, 2_000_000, 5_000_000, 10_000_000, 20_000_000],
        value=2_000_000,
    )
    n_candidates = st.slider("비교할 조합 개수", 10, 150, 50)

    my_portfolio = st.session_state.get("portfolio") or []
    include_mine = False
    if my_portfolio:
        include_mine = st.checkbox(f"'번호 생성' 탭에서 만든 내 {len(my_portfolio)}게임도 같이 비교", value=True)

    if st.button("⚖️ 비교 실행"):
        candidates = generator.generate_portfolio(size=n_candidates, seed=None)
        if include_mine:
            candidates = list(dict.fromkeys(list(my_portfolio) + candidates))  # dedupe, keep order
        with st.spinner(f"{n_draws:,}회 × {len(candidates)}개 조합 동시 채점 중..."):
            result = monte_carlo.compare_candidates(candidates, n_draws=n_draws, seed=None)

        c1, c2, c3 = st.columns(3)
        c1.metric("이론적 기대 적중", f"{result['theoretical_mean']:.4f}")
        c2.metric("후보 간 표준편차", f"{result['std_across_candidates']:.6f}")
        c3.metric("순수 노이즈 예측치", f"{result['expected_noise_std']:.6f}")

        if result["max_abs_z"] < 3.0:
            st.success(f"✅ {result['verdict']} (최대 |z| = {result['max_abs_z']:.2f})")
        else:
            st.warning(f"⚠️ {result['verdict']} (최대 |z| = {result['max_abs_z']:.2f})")

        ranked = result["ranked"]
        top10 = ranked[:10]
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=[str(r["ticket"]) for r in top10],
            y=[r["mean_matches"] for r in top10],
            error_y=dict(type="data", array=[result["expected_noise_std"]] * len(top10)),
            marker_color="#69c8f2",
        ))
        fig.add_hline(y=result["theoretical_mean"], line_dash="dash", line_color="#ff7272",
                       annotation_text="이론값 0.8")
        fig.update_layout(
            title="상위 10개 조합 (오차막대 = ±1 표준오차, 이론선과 겹치면 유의미하지 않음)",
            xaxis_title="조합", yaxis_title="평균 적중 개수", xaxis_tickangle=-45,
        )
        st.plotly_chart(fig, width="stretch")

        st.dataframe(pd.DataFrame([
            {"순위": r["rank"], "조합": str(r["ticket"]), "평균적중": round(r["mean_matches"], 6),
             "z (이론값 대비)": round(r["z_vs_theoretical"], 2)}
            for r in ranked
        ]), width="stretch", hide_index=True)

        st.caption(
            "재현성 확인: 이 버튼을 다시 누르면 (매번 새 시드로 돌기 때문에) 1위 조합이 "
            "바뀌는 걸 볼 수 있습니다 -- 진짜 신호였다면 순위가 안정적으로 유지되어야 합니다."
        )


def page_backtest():
    st.title("⏮ Walk-forward 백테스트 & 통계적 유의성 검증")
    draws = db.get_all_draws()
    if len(draws) < 60:
        st.warning("백테스트에 충분한 데이터가 없습니다 (최소 약 60회차 필요).")
        return
    min_history = st.slider("최소 학습 기간(회차)", 20, min(200, len(draws) - 10), 52)
    if st.button("백테스트 실행"):
        with st.spinner("Walk-forward 백테스트 실행 중 (미래 데이터 누출 없음, 매 회차마다 이전 데이터로만 생성)..."):
            res = walkforward.walk_forward_backtest(draws, min_history=min_history, seed=7)
            sig = significance.compare_strategies(res["v3_hits_by_round"], res["baseline_hits_by_round"])
        st.write(f"테스트 회차 수: {res['n_tested_rounds']} (회차 {res['round_range'][0]} ~ {res['round_range'][1]})")
        c1, c2 = st.columns(2)
        c1.metric("V3 평균 최고 적중", f"{res['v3_mean_best_match']:.3f}")
        c2.metric("랜덤 baseline 평균 최고 적중", f"{res['baseline_mean_best_match']:.3f}")
        st.write(f"**통계적 유의성 (paired t-test):** p = {sig['paired_ttest']['p_value']:.4f}")
        st.write(sig["interpretation"])


def page_play():
    st.title("🎰 로또 추첨 플레이")
    st.caption("실제 추첨 방식처럼 번호를 하나씩 뽑습니다. 버튼을 눌러 시작하세요.")

    if "my_ticket" not in st.session_state:
        st.session_state["my_ticket"] = sorted(
            int(x) for x in np.random.default_rng().choice(range(1, 46), size=6, replace=False)
        )

    st.subheader("내 번호")
    picked = st.multiselect(
        "6개 번호를 직접 선택하거나, 자동 생성을 사용하세요.",
        options=list(range(1, 46)),
        default=st.session_state["my_ticket"],
        max_selections=6,
    )
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🎲 자동 번호 생성"):
            st.session_state["my_ticket"] = list(generator.generate_portfolio(size=1, seed=None)[0])
            st.rerun()
    with col_b:
        start_disabled = len(picked) != 6
        start = st.button("▶ 추첨 시작", disabled=start_disabled, type="primary")
        if start_disabled:
            st.caption("번호 6개를 모두 선택해야 추첨을 시작할 수 있습니다.")

    if len(picked) == 6:
        st.session_state["my_ticket"] = sorted(picked)
        st.markdown(render_balls(st.session_state["my_ticket"]), unsafe_allow_html=True)

    if start and len(picked) == 6:
        my_ticket = sorted(st.session_state["my_ticket"])
        pool = list(range(1, 46))
        rng = np.random.default_rng()
        rng.shuffle(pool)
        drawn_main = pool[:6]
        bonus = pool[6]

        st.divider()
        components.html(render_draw_machine(my_ticket, drawn_main, bonus), height=640, scrolling=False)


PAGES = {
    "🎰 추첨 플레이": page_play,
    "💼 번호 생성": page_portfolio,
    "개요": page_overview,
    "통계 분석": page_statistics,
    "확률 엔진": page_probability,
    "🔬 정밀 통계 검증": page_randomness,
    "Monte Carlo": page_simulation,
    "⚖️ 조합 비교": page_noise_check,
    "백테스트": page_backtest,
}


def sidebar_data_refresh():
    st.sidebar.header("데이터")
    db.init_db()
    latest = db.get_latest_round()
    st.sidebar.caption(f"DB 최신 회차: {latest if latest else '없음'}")
    min_sources = st.sidebar.slider("뉴스 교차검증 최소 언론사 수", 2, 5, 2)
    if st.sidebar.button("🔎 새 회차 확인 (뉴스 검색 자동화)"):
        with st.sidebar:
            with st.spinner("Google 뉴스에서 신규 회차 검색 및 다중 언론사 교차검증 중..."):
                base_round = latest or 0
                new_draws = news_search.discover_new_rounds(base_round, min_sources=min_sources)
                for d in new_draws:
                    db.upsert_draw(d.round, d.draw_date, list(d.numbers), d.bonus,
                                    source=f"google_news_search(min_sources={min_sources})", verified=True)
            if new_draws:
                st.success(f"신규 {len(new_draws)}개 회차 저장 완료 (언론사 {min_sources}곳 이상 일치 확인)")
            else:
                st.info("신규 회차 없음 (아직 추첨 전이거나, 아직 충분한 언론사 보도가 없음)")
            load_history_df.clear()


def main():
    sidebar_data_refresh()
    # Tabs (not a sidebar radio) so navigation is visible in the main body on
    # mobile too -- Streamlit auto-collapses the sidebar on narrow viewports,
    # which made every page except the default one invisible on phones.
    tabs = st.tabs(list(PAGES.keys()))
    for tab, page_fn in zip(tabs, PAGES.values()):
        with tab:
            page_fn()


if __name__ == "__main__":
    main()
