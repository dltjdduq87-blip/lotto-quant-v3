"""LOTTO 6/45 QUANT V3 -- Streamlit dashboard.

Run with:  streamlit run lotto_quant_v3/dashboard/app.py
(from the project root, so the lotto_quant_v3 package resolves)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Make the repo root importable regardless of streamlit's script-dir sys.path quirk.
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lotto_quant_v3.backtest import walkforward
from lotto_quant_v3.dashboard import visuals
from lotto_quant_v3.dashboard.visuals import VIZ, ball_color, render_balls, render_draw_machine
from lotto_quant_v3.data import db, news_search, results_feed
from lotto_quant_v3.optimization import optimizer
from lotto_quant_v3.popularity import model as popularity
from lotto_quant_v3.portfolio import generator, probability
from lotto_quant_v3.probability import engine as prob_engine
from lotto_quant_v3.probability import prize_model
from lotto_quant_v3.simulation import monte_carlo, strategy_lab
from lotto_quant_v3.statistics import analysis, randomness_tests, significance

st.set_page_config(page_title="LOTTO 6/45 QUANT V3", page_icon="🎱", layout="wide")


def inject_custom_css():
    st.markdown(visuals.global_css(), unsafe_allow_html=True)


def styled_layout(fig: go.Figure, title: str, xaxis_title: str = "", yaxis_title: str = "") -> go.Figure:
    """Apply the shared dark chart theme (surface, grid, ink) to a plotly figure."""
    fig.update_layout(
        title=title,
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
        paper_bgcolor=VIZ["surface"],
        plot_bgcolor=VIZ["surface"],
        font=dict(color=VIZ["ink_muted"]),
        title_font=dict(color=VIZ["ink"]),
        xaxis=dict(gridcolor=VIZ["grid"], zerolinecolor=VIZ["grid"], color=VIZ["axis_muted"]),
        yaxis=dict(gridcolor=VIZ["grid"], zerolinecolor=VIZ["grid"], color=VIZ["axis_muted"]),
        margin=dict(t=48, l=10, r=10, b=10),
        transition=dict(duration=450, easing="cubic-out"),
    )
    return fig


TIER_NAMES = {0: "낙첨", 1: "1등", 2: "2등", 3: "3등", 4: "4등", 5: "5등"}


def tier_table(best_tier: dict) -> pd.DataFrame:
    rows = []
    for k in range(1, 6):
        pk = best_tier[k]
        rows.append({"최고 등수": TIER_NAMES[k], "확률": f"{pk*100:.6f}%",
                     "약 몇 회에 한 번": f"1 / {1/pk:,.0f}" if pk > 0 else "-"})
    rows.append({"최고 등수": "낙첨", "확률": f"{best_tier[0]*100:.4f}%", "약 몇 회에 한 번": "-"})
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600)
def load_history_df():
    draws = db.get_all_draws()
    if not draws:
        return None
    return analysis.draws_to_frame(draws)


@st.cache_data(ttl=3600)
def load_stats():
    return db.get_all_stats()


@st.cache_resource(show_spinner=False)
def load_popularity_model(latest_round: int):
    """Fitted once per data version (the argument is only the cache key)."""
    try:
        return popularity.fit(load_stats())
    except ValueError:
        return None


@st.cache_data(show_spinner=False)
def load_holdout(latest_round: int):
    return popularity.holdout_validation(load_stats())


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def auto_sync(due_round: int) -> dict:
    """Pull rounds the DB is missing from the result feed. Cached, so the feed is asked at most
    once per 6 hours per missing round; a failure is returned (not raised) so the app still opens."""
    try:
        return results_feed.sync(db)
    except Exception as exc:  # network down, feed format changed, ...
        return {"error": str(exc), "new_rounds": []}


def ensure_fresh_data() -> dict | None:
    db.init_db()
    latest = db.get_latest_round() or 0
    due = news_search.most_recent_draw_round()
    if latest >= due and len(load_stats()) >= latest:
        return None
    report = auto_sync(due)
    if report.get("new_rounds") and (db.get_latest_round() or 0) > latest:
        load_history_df.clear()
        load_stats.clear()
    return report


def page_overview():
    st.markdown(
        visuals.hero("🎱", "LOTTO 6/45 QUANT V3",
                     "확률 계산 · 당첨금 나눠 갖기 분석 · 통계 검증. 당첨 번호를 맞히는 도구가 아니라, "
                     "같은 확률에서 손해를 덜 보는 방법을 숫자로 확인하는 도구입니다."),
        unsafe_allow_html=True,
    )
    df = load_history_df()
    if df is None:
        st.warning("DB에 데이터가 없습니다. 사이드바에서 '최신 회차 받아오기'를 먼저 실행하세요.")
        return
    latest = df.iloc[-1]
    st.markdown(f"**{int(latest['round'])}회 당첨번호** · {latest['date']} 추첨")
    st.markdown(render_balls(latest["numbers"], latest["bonus"], size=54), unsafe_allow_html=True)

    stats = {r["round"]: r for r in load_stats()}.get(int(latest["round"]))
    if stats and stats.get("w1") is not None:
        split = ""
        if stats.get("auto") is not None:
            split = f"자동 {stats['auto']}명 · 수동 {(stats.get('manual') or 0) + (stats.get('semi_auto') or 0)}명"
        tiles = [
            {"label": "1등 한 명이 받은 돈 (세전)", "value": (stats["p1"] or 0) / 1e8, "unit": "억원", "decimals": 1,
             "note": "당첨자끼리 똑같이 나눈 금액", "gold": True},
            {"label": "1등 당첨자", "value": stats["w1"], "unit": "명", "note": split},
            {"label": "이번 회차 판매액", "value": stats["sales"] / 1e8, "unit": "억원", "note": "이 중 절반이 당첨금"},
            {"label": "보유 회차", "value": len(df), "unit": "회", "note": "1회부터 빠짐없이"},
        ]
        st.iframe(visuals.stat_strip(tiles), height="content")
    else:
        c1, c2 = st.columns(2)
        c1.metric("최신 회차", int(latest["round"]))
        c2.metric("DB 보유 회차 수", len(df))
    st.caption("데이터 출처: 1~1239회는 사용자 제공 이력(엑셀)과 공개 결과 미러(smok95.github.io/lotto)를 "
               "전 회차 대조해 일치를 확인했습니다. 이후 회차는 같은 미러에서 자동으로 받아오며, "
               "당첨자 수 · 당첨금 · 판매액도 함께 저장합니다. 동행복권 공식 API는 2026-01 개편 이후 접근이 막혀 있습니다.")


def page_statistics():
    st.title("📊 통계 분석")
    df = load_history_df()
    if df is None:
        st.warning("데이터가 없습니다.")
        return
    freq = analysis.number_frequency(df)
    fig = go.Figure(go.Bar(x=freq.index, y=freq.values, marker_color=[ball_color(n) for n in freq.index]))
    styled_layout(fig, "번호별 출현 빈도", "번호", "출현 횟수")
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
    fig2 = go.Figure(go.Histogram(x=sums, nbinsx=30, marker_color=VIZ["accent"]))
    styled_layout(fig2, f"번호 합계 분포 (평균={sums.mean():.1f}, 표준편차={sums.std():.1f})", "합계", "빈도")
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

    st.subheader("💰 등수별 실제 기대 당첨금 (세전 · 세후)")
    st.caption(
        "판매액의 50%가 당첨금 → 4등(5만원)·5등(5천원)을 먼저 주고, 남은 돈을 1등 75% · 2등 12.5% · 3등 12.5%로 "
        "나눠 그 등수 당첨자끼리 똑같이 나눕니다. 그래서 1~3등 금액은 '같은 회차에 몇 명이 같이 당첨되느냐'에 달려 있고, "
        "여기서는 그 인원을 확률적으로(포아송) 반영했습니다. 세금: 200만원 이하 비과세, 초과 시 3억까지 22%, 3억 초과분 33%."
    )
    sales_eok = st.slider("회차당 판매액 (억원)", 500, 2000, int(prize_model.DEFAULT_SALES_PER_ROUND / 1e8), step=10,
                          help="2025년 연간 판매액 약 6.2조원 → 회차당 약 1,190억원")
    model = prize_model.PrizeModel(sales_eok * 1e8)
    st.dataframe(pd.DataFrame([{
        "등수": TIER_NAMES[r["tier"]],
        "회차당 평균 당첨 게임 수": f"{r['expected_winners']:,.1f}",
        "1게임 기대 당첨금(세전)": f"{r['prize_gross']:,.0f}원",
        "세후 실수령": f"{r['prize_net']:,.0f}원",
        "1,000원당 기대값(세후)": f"{r['ev_net']:,.1f}원",
    } for r in model.table()]), width="stretch", hide_index=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("기대 회수율 (세전)", f"{model.expected_return()*100:.1f}%")
    c2.metric("기대 회수율 (세후)", f"{model.expected_return(net=True)*100:.1f}%")
    c3.metric("1,000원당 평균 손실 (세후)", f"{(1-model.expected_return(net=True))*1000:,.0f}원")
    st.caption("판매액이 늘면 1~3등 당첨자 수도 같이 늘어 1게임당 금액은 거의 그대로입니다 — 회수율은 판매액과 무관하게 세전 약 50%.")


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

        n_reject = result["tests_rejecting_null_holm"]
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
            st.write(f"χ² = {chi2['statistic']:.2f}, dof = {chi2['dof']} "
                     f"(비복원추출 보정 전 {chi2['statistic_uncorrected']:.2f})")
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
        st.subheader("다중검정 보정 (Holm)")
        st.caption(
            "검정을 여러 개 돌리면 데이터가 진짜 무작위여도 하나쯤은 우연히 p<0.05가 나올 수 있습니다. "
            "Holm 보정은 이를 감안해 p-value를 키워서, '하나라도 거짓 경보가 날 확률'을 5% 이하로 묶습니다. "
            "카이제곱은 한 회차 6개 번호가 중복 없이 뽑힌다는 점(비복원추출)을 반영해 보정했습니다."
        )
        st.dataframe(pd.DataFrame([{
            "검정": k, "p-value": round(v, 4), "Holm 보정 p": round(result["p_values_holm"][k], 4),
            "판정": "기각(이상 징후)" if result["p_values_holm"][k] < 0.05 else "통과",
        } for k, v in result["p_values_raw"].items()]), width="stretch", hide_index=True)
        if result.get("bonus_uniformity"):
            st.caption(f"보너스 번호 균등성: χ² = {result['bonus_uniformity']['statistic']:.2f}, "
                       f"p = {result['bonus_uniformity']['p_value']:.4f}")


def page_portfolio():
    st.title("💼 포트폴리오 생성 & 정확 확률")
    df = load_history_df()
    mode = st.radio("생성 방식", ["덜 나눠 갖는 번호 (추천)", "균등 랜덤 (baseline)", "빈도 가중 (V3)",
                              "분산 최적화 (V3 optimizer)"],
                    help="당첨 확률은 네 방식 모두 똑같습니다. '덜 나눠 갖는 번호'만 당첨됐을 때 받는 돈이 달라집니다.")
    pop_model = load_popularity_model(db.get_latest_round() or 0)

    use_fixed_seed = st.checkbox("시드 고정 (재현용 -- 끄면 매번 새로운 무작위 번호)", value=False)
    seed = None
    if use_fixed_seed:
        seed = int(st.number_input("시드 값", value=0, step=1))

    weights = None
    if mode in ("빈도 가중 (V3)", "분산 최적화 (V3 optimizer)") and df is not None:
        weights = (analysis.number_frequency(df).values + 1).astype(float)

    if st.button("5게임 생성", type="primary"):
        if mode == "덜 나눠 갖는 번호 (추천)" and pop_model is not None:
            tickets = popularity.suggest_portfolio(pop_model, games=5, seed=seed)
        elif mode == "분산 최적화 (V3 optimizer)":
            tickets = optimizer.optimize_portfolio(weights=weights, seed=seed)
        else:
            tickets = generator.generate_portfolio(weights=weights, seed=seed)
        st.session_state["portfolio"] = tickets

    tickets = st.session_state.get("portfolio")
    if tickets:
        for i, t in enumerate(tickets, 1):
            note = ""
            if pop_model is not None:
                note = f" · 1등 당첨 시 나눠 갖는 정도 평균의 {pop_model.multiplier(t):.2f}배"
            st.markdown(f"**게임 {i}**{note}")
            st.markdown(render_balls(t, size=40), unsafe_allow_html=True)

        if st.button("이 포트폴리오의 정확 당첨 확률 계산 (전수조사, 1초 이내)"):
            with st.spinner("C(45,6) = 8,145,060개 조합 전수 계산 중..."):
                result = probability.exact_portfolio_distribution(tickets)
            c1, c2, c3 = st.columns(3)
            c1.metric("5등 이상 하나라도", f"{result['any_prize_probability']*100:.3f}%")
            c2.metric("1등 확률", f"1 / {1/result['jackpot_probability']:,.0f}")
            c3.metric("단순 합계 대비 줄어든 몫", f"{result['overlap_loss']*100:.3f}%p",
                      help="게임별 당첨 확률을 그냥 더한 값과 '하나라도 당첨될 확률'의 차이입니다. 한 회차에 두 게임 이상이 "
                           "같이 당첨되는 경우가 있어 생기며, 게임끼리 번호가 많이 겹칠수록 커집니다(겹침 0이어도 0은 아님). "
                           "기대 당첨금 자체는 변하지 않습니다.")
            st.dataframe(tier_table(result["best_tier_probability"]), width="stretch", hide_index=True)
            st.caption("보너스 번호까지 포함해 C(45,6)=8,145,060개 추첨 결과를 전부 계산한 정확값입니다 (표본 아님).")


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
        st.metric("5등 이상 하나라도 당첨된 회차 비율", f"{mc['any_prize_probability']*100:.3f}%")
        st.dataframe(pd.DataFrame([{
            "최고 등수": TIER_NAMES[k], "횟수": mc["best_tier_counts"][k],
            "비율": f"{mc['best_tier_probability'][k]*100:.4f}%",
        } for k in (1, 2, 3, 4, 5, 0)]), width="stretch", hide_index=True)
        fig = go.Figure(go.Bar(x=list(mc["counts"].keys()), y=list(mc["counts"].values()), marker_color=VIZ["accent"]))
        styled_layout(fig, "최고 적중 개수 분포", "일치 개수", "횟수")
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
            error_y=dict(type="data", array=[result["expected_noise_std"]] * len(top10), color=VIZ["ink_muted"]),
            marker_color=VIZ["accent"],
        ))
        fig.add_hline(y=result["theoretical_mean"], line_dash="dash", line_color=VIZ["critical"],
                       annotation_text="이론값 0.8", annotation_font_color=VIZ["critical"])
        styled_layout(
            fig, "상위 10개 조합 (오차막대 = ±1 표준오차, 이론선과 겹치면 유의미하지 않음)",
            "조합", "평균 적중 개수",
        )
        fig.update_layout(xaxis_tickangle=-45)
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
        st.iframe(render_draw_machine(my_ticket, drawn_main, bonus), height=720)


def page_strategy_lab():
    st.title("🧪 시뮬레이션 랩")
    st.caption(
        "번호 고르는 방법을 실제 과거 추첨에 그대로 대입해 봅니다. 매 회차마다 그 회차 **이전** 데이터만 써서 "
        "번호를 만들고(미래 정보 사용 없음), 무작위 시드를 여러 번 바꿔 반복해서 운에 좌우되지 않게 했습니다. "
        "당첨 판정은 보너스 번호까지 포함한 실제 등수 기준입니다."
    )
    tab_a, tab_b = st.tabs(["📜 번호 선택 방법 비교 (과거 대입)", "💸 평생 구매 시뮬레이션"])

    with tab_a:
        draws = db.get_all_draws()
        if len(draws) < 80:
            st.warning("과거 데이터가 부족합니다.")
        else:
            c1, c2, c3 = st.columns(3)
            n_rep = c1.select_slider("반복 횟수(시드)", options=[1, 3, 5, 10, 20], value=5)
            games = c2.slider("회차당 게임 수", 1, 10, 5)
            last_n = c3.select_slider("검증할 최근 회차 수", options=[200, 500, 800, "전체"], value=500)
            if st.button("▶ 비교 실행", key="lab_run"):
                bar = st.progress(0.0, text="과거 회차에 하나씩 대입하는 중...")
                res = strategy_lab.strategy_walkforward(
                    draws, n_repeats=n_rep, games=games,
                    last_n_rounds=None if last_n == "전체" else int(last_n),
                    progress=lambda f: bar.progress(min(f, 1.0), text=f"대입 중... {f*100:.0f}%"),
                )
                bar.empty()
                st.session_state["lab_res"] = res
            res = st.session_state.get("lab_res")
            if res and "ci_level" not in res:  # result from an older version of this page
                res = None
            if res:
                st.write(f"검증 회차 {res['round_range'][0]}~{res['round_range'][1]} ({res['n_rounds']}회) × "
                         f"{res['games']}게임 × 시드 {res['n_repeats']}번")
                table = pd.DataFrame([{
                    "전략": r["전략"],
                    "5등 이상 당첨률(게임당)": f"{r['5등 이상 당첨률(게임당)']*100:.2f}%",
                    "이론값과 차이(z)": round(r["5등 이상 당첨률 z(이론 대비)"], 2),
                    "회수율(세전)": f"{r['회수율']*100:.1f}%",
                    "회수율(세후)": f"{r['회수율(세후)']*100:.1f}%",
                    "무작위와 다름?": "예" if r["기준과 다르다고 볼 수 있음"] else "아니오",
                    "평균 최고 일치": round(r["평균 최고 일치 개수"], 3),
                    "게임 간 겹친 번호": round(r["게임 간 겹친 번호 수"], 2),
                    "4등": r["등수별 횟수"][4], "3등": r["등수별 횟수"][3], "2등": r["등수별 횟수"][2], "1등": r["등수별 횟수"][1],
                } for r in res["rows"]])
                st.dataframe(table, width="stretch", hide_index=True)
                fig = go.Figure(go.Bar(
                    x=[r["전략"] for r in res["rows"]],
                    y=[r["5등 이상 당첨률(게임당)"] * 100 for r in res["rows"]],
                    marker_color=VIZ["accent"],
                ))
                fig.add_hline(y=res["theory_5th_or_better"] * 100, line_dash="dash", line_color=VIZ["critical"],
                              annotation_text=f"이론값 {res['theory_5th_or_better']*100:.2f}%",
                              annotation_font_color=VIZ["critical"])
                styled_layout(fig, "전략별 5등 이상 당첨률 (게임당)", "", "%")
                st.plotly_chart(fig, width="stretch")
                st.info(
                    "읽는 법: '이론값과 차이(z)'가 ±2 안이면 무작위와 구분이 안 되는 수준입니다. "
                    "z는 같은 회차 게임끼리 독립이 아니라는 점을 반영해 회차 단위로 계산했습니다. "
                    "'평균 최고 일치'는 한 회차 5게임 중 가장 많이 맞은 개수의 평균이라, 게임끼리 번호가 덜 겹칠수록 "
                    "자연히 올라갑니다(예측력이 아니라 번호를 넓게 펼친 효과). '무작위와 다름?'은 여러 전략을 동시에 "
                    f"비교하는 점을 보정한 {res['ci_level']*100:.1f}% 구간으로 판정합니다. 상금은 판매액 50% 배분 규칙과 "
                    f"공동 당첨자 수를 반영한 기대값(1등 {res['prizes'][1]/1e8:.1f}억, 2등 {res['prizes'][2]/1e4:,.0f}만, "
                    f"3등 {res['prizes'][3]/1e4:,.0f}만)이고, 세후는 복권 세금(22%/33%)을 뺀 값입니다. "
                    f"이론 기대 회수율: 세전 {res['theory_return']*100:.1f}% · 세후 {res['theory_return_net']*100:.1f}%. "
                    "실제 표본 회수율은 3등 한두 번에도 크게 흔들립니다."
                )

    with tab_b:
        c1, c2, c3 = st.columns(3)
        gpw = c1.slider("매주 게임 수", 1, 20, 5, key="life_g")
        years = c2.slider("기간(년)", 1, 50, 30, key="life_y")
        paths = c3.select_slider("시뮬레이션 인생 수", options=[10_000, 100_000, 500_000], value=100_000)
        net = st.toggle("세금 뺀 실수령 기준", value=True, key="life_net")
        lt = strategy_lab.lifetime_simulation(gpw, years, paths, seed=None, net=net)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 구매액", f"{lt['spent']:,.0f}원")
        m2.metric("중간값 손익", f"{lt['median_net']:,.0f}원")
        m3.metric("본전 이상일 확률", f"{lt['p_net_positive']*100:.2f}%")
        m4.metric("1등 한 번이라도 (정확 계산)", f"{lt['p_tier'][1]*100:.3f}%")
        st.write(
            f"기대 회수율 {lt['expected_return_rate']*100:.1f}% ({'세후' if net else '세전'} 이론값, 1등 상금 포함) · 중간값 회수율 "
            f"{lt['median_return_rate']*100:.1f}% (대부분 사람이 실제로 겪는 값) · 3등 이상 한 번이라도 "
            f"{lt['p_tier'][3]*100:.1f}% (정확 계산)"
        )
        st.caption(f"이번 시뮬레이션 표본 평균 회수율 {lt['sample_mean_return_rate']*100:.1f}% — 1등 같은 드문 "
                   "고액 당첨 때문에 실행할 때마다 크게 흔들려서, 위 기대 회수율은 정확한 계산값을 씁니다.")
        fig = go.Figure(go.Histogram(x=lt["net_samples"] / 10_000, nbinsx=80, marker_color=VIZ["accent"]))
        styled_layout(fig, "평생 손익 분포 (만원, 1등 당첨 같은 극단값은 오른쪽 끝)", "손익(만원)", "인생 수")
        st.plotly_chart(fig, width="stretch")


def _eok(v: float) -> str:
    return f"{v / 1e8:,.1f}억원"


def _chance(p: float) -> str:
    """A p-value in plain words."""
    if p < 1e-6:
        return "100만 분의 1도 안 됩니다"
    if p < 0.001:
        return f"약 {1 / p:,.0f}분의 1입니다"
    return f"{p * 100:.1f}%입니다"


def page_share():
    st.markdown(
        visuals.hero("💎", "당첨금 지키기",
                     "어떤 번호를 골라도 당첨 확률은 똑같습니다. 달라지는 건 당첨됐을 때 몇 명과 나눠 갖느냐입니다. "
                     "1~3등 당첨금은 같은 번호를 맞힌 사람끼리 똑같이 나누기 때문입니다.",
                     balls=(29, 36, 41, 43, 44, 45)),
        unsafe_allow_html=True,
    )
    latest_round = db.get_latest_round() or 0
    model = load_popularity_model(latest_round)
    if model is None:
        st.warning("당첨자 수 데이터가 부족합니다. 사이드바에서 '최신 회차 받아오기'를 눌러 주세요.")
        return
    df = load_history_df()
    last_draw = df.iloc[-1]["numbers"] if df is not None else None
    prize = prize_model.PrizeModel()

    st.subheader("내 번호는 몇 명과 나눠 갖게 될까")
    tickets = st.session_state.get("portfolio") or []
    default = list(st.session_state.get("my_ticket") or (tickets[0] if tickets else (5, 14, 22, 31, 38, 45)))
    picked = st.multiselect("번호 6개를 고르세요", options=list(range(1, 46)), default=default,
                            max_selections=6, key="share_pick")
    if len(picked) == 6:
        ticket = tuple(sorted(picked))
        v = model.ticket_value(ticket, prize)
        st.markdown(render_balls(ticket, size=50), unsafe_allow_html=True)
        st.markdown(visuals.share_meter(v["multiplier"], model.floor, float(model.reference()[-1])),
                    unsafe_allow_html=True)
        diff = v["jackpot_net"] / v["jackpot_net_avg"] - 1
        tone = "lqv-up" if diff >= 0 else "lqv-down"
        c1, c2, c3 = st.columns(3)
        c1.markdown(visuals.card(
            "1등 당첨 시 받는 돈 (세후)", _eok(v["jackpot_net"]),
            f'평균 조합 {_eok(v["jackpot_net_avg"])} 대비 <span class="{tone}">{diff*100:+.0f}%</span>'),
            unsafe_allow_html=True)
        pct = v["percentile"]
        rank = (f"전체 조합 중 덜 나눠 갖는 쪽 상위 {max(pct, 0.001)*100:.1f}%" if pct < 0.5
                else f"전체 조합 중 많이 나눠 갖는 쪽 상위 {max(1 - pct, 0.001)*100:.1f}%")
        c2.markdown(visuals.card("같이 당첨되는 사람 수", f'평균의 {v["multiplier"]:.2f}배', rank),
                    unsafe_allow_html=True)
        c3.markdown(visuals.card(
            "1,000원당 기대 회수 (세후)", f'{v["return_net"]*1000:,.0f}원',
            f'평균 조합 {v["return_net_avg"]*1000:,.0f}원 · 여전히 1,000원보다 적습니다'),
            unsafe_allow_html=True)
        for flag in popularity.pattern_flags(ticket, last_draw):
            st.warning(flag + " 이런 모양은 위 계산보다 실제로 훨씬 많이 겹칠 수 있습니다.")
    else:
        st.info("번호 6개를 모두 고르면 계산합니다.")

    st.divider()
    st.subheader("덜 나눠 갖는 번호로 5게임 만들기")
    st.caption("덜 나눠 갖는 쪽 상위 3% 조합 수십만 개 중에서 무작위로 고릅니다. 누를 때마다 다른 번호가 나옵니다.")
    if st.button("💎 5게임 만들기", type="primary", key="share_make"):
        st.session_state["portfolio"] = popularity.suggest_portfolio(model, games=5)
        st.session_state["share_made"] = True
    if st.session_state.get("share_made") and st.session_state.get("portfolio"):
        for i, t in enumerate(st.session_state["portfolio"], 1):
            tv = model.ticket_value(t, prize)
            st.markdown(f"**게임 {i}** · 1등 당첨 시 세후 약 {_eok(tv['jackpot_net'])} "
                        f"(평균 조합보다 {(tv['jackpot_net']/tv['jackpot_net_avg']-1)*100:+.0f}%)")
            st.markdown(render_balls(t, size=40), unsafe_allow_html=True)
        st.caption("이 5게임은 '번호 생성' · 'Monte Carlo' 탭에도 그대로 넘어갑니다.")

    st.divider()
    st.subheader("사람들이 많이 고르는 번호, 덜 고르는 번호")
    st.markdown(visuals.popularity_grid(100 * np.exp(model.slope * model.beta)), unsafe_allow_html=True)
    st.caption(f"{model.round_range[0]}–{model.round_range[1]}회 당첨자 수로 추정한, 직접 번호를 고르는 사람들의 선호입니다. "
               "작은 번호와 7 · 12 · 17 같은 번호에 몰리고, 29와 40번대는 덜 고릅니다. "
               "덜 고른다고 더 잘 나오는 것은 아닙니다 — 나왔을 때 나눠 가질 사람이 적을 뿐입니다.")

    st.divider()
    st.subheader("이게 진짜인지: 처음 보는 회차로 검증")
    hold = load_holdout(latest_round)
    labels = ["가장 덜 고르는\n번호가 나온 회차", "덜 고르는 편", "중간", "많이 고르는 편", "가장 많이 고르는\n번호가 나온 회차"]
    prizes = [g["avg_prize"] / 1e8 for g in hold["groups"]]
    fig = go.Figure(go.Bar(
        x=[label.replace("\n", "<br>") for label in labels], y=prizes,
        marker_color=[VIZ["accent"]] * 5, text=[f"{p:.1f}억" for p in prizes], textposition="outside",
        textfont=dict(color=VIZ["ink"]), cliponaxis=False,
        hovertemplate="%{x}<br>1등 1인당 평균 %{y:.1f}억원<extra></extra>",
    ))
    styled_layout(fig, "많이 고르는 번호가 나온 회차는 1등 한 명이 받은 돈이 적었습니다 (1인당 실제 당첨금, 억원)")
    fig.update_layout(margin=dict(t=56, l=10, r=10, b=10), yaxis_range=[0, max(prizes) * 1.18])
    st.plotly_chart(fig, width="stretch")
    st.info(
        f"번호 선호는 {hold['train_rounds'][0]}–{hold['train_rounds'][1]}회만 보고 계산했고, 위 막대는 그 계산에 "
        f"쓰지 않은 {hold['test_rounds'][0]}–{hold['test_rounds'][1]}회({hold['n_test']}회)의 실제 결과입니다. "
        f"번호 선호와 1등 당첨자 수가 무관한데 우연히 이만큼 맞아떨어질 확률은 {_chance(hold['p_value'])}. "
        f"자동 구매 당첨자 수는 번호와 무관했고(우연일 확률 {model.p_auto*100:.0f}%), 수동 구매 당첨자 수만 번호에 따라 "
        "달라졌습니다. 자동은 번호를 고르지 않으니 그래야 맞습니다."
    )
    best = tuple(int(n) + 1 for n in np.argsort(model.beta)[:6])
    best_return = model.ticket_value(best, prize)["return_net"]
    with st.expander("한계와 주의할 점"):
        st.markdown(
            f"- **당첨 확률은 전혀 오르지 않습니다.** 1등 확률은 어떤 번호든 1/8,145,060입니다.\n"
            f"- **줄일 수 있는 폭에 한계가 있습니다.** 1등 당첨자의 약 {model.auto_share/(model.auto_share+model.manual_share)*100:.0f}%는 "
            f"자동 구매라 어떤 번호든 똑같이 겹칩니다. 그래서 나눠 갖는 정도는 평균의 {model.floor:.2f}배 아래로 내려갈 수 없습니다.\n"
            f"- **여전히 손해 보는 게임입니다.** 가장 유리한 조합도 1,000원당 기대 회수가 세후 {best_return*1000:,.0f}원입니다.\n"
            "- **번호 하나하나의 인기만 봅니다.** 1-2-3-4-5-6처럼 모양으로 찍는 조합은 실제로 훨씬 많이 겹치는데, "
            "이 계산에는 일부만 반영됩니다(위 경고 문구로 따로 알려 드립니다).\n"
            "- **1등이 나와야 의미가 있습니다.** 평생 1등을 한 번도 못 맞힐 가능성이 압도적으로 높고, "
            "그 경우 이 방법으로 달라지는 것은 3등 당첨금 정도입니다."
        )


PAGES = {
    "🎰 추첨 플레이": page_play,
    "💎 당첨금 지키기": page_share,
    "💼 번호 생성": page_portfolio,
    "개요": page_overview,
    "통계 분석": page_statistics,
    "확률 엔진": page_probability,
    "🔬 정밀 통계 검증": page_randomness,
    "Monte Carlo": page_simulation,
    "⚖️ 조합 비교": page_noise_check,
    "백테스트": page_backtest,
    "🧪 시뮬레이션 랩": page_strategy_lab,
}


def sidebar_data_refresh():
    st.sidebar.header("데이터")
    report = ensure_fresh_data()
    latest = db.get_latest_round()
    st.sidebar.caption(f"DB 최신 회차: {latest if latest else '없음'}")
    if report and report.get("new_rounds"):
        st.sidebar.success(f"새 회차 {len(report['new_rounds'])}개를 자동으로 받아왔습니다.")
    elif report and report.get("error"):
        st.sidebar.warning("새 회차를 자동으로 받아오지 못했습니다. 잠시 뒤 아래 버튼으로 다시 시도하세요.")
    if st.sidebar.button("⬇️ 최신 회차 받아오기 (당첨자 수 · 당첨금 포함)"):
        with st.sidebar:
            with st.spinner("결과 미러에서 받아오는 중..."):
                try:
                    manual = results_feed.sync(db)
                except Exception as exc:
                    st.error(f"받아오지 못했습니다: {exc}")
                else:
                    if manual["conflicts"]:
                        st.warning(f"기존 데이터와 번호가 다른 회차가 있어 그대로 두었습니다: {manual['conflicts']}")
                    st.success(f"새 회차 {len(manual['new_rounds'])}개 · 통계 {manual['stats_rows']}회차 저장")
                    load_history_df.clear()
                    load_stats.clear()
                    auto_sync.clear()
    st.sidebar.divider()
    st.sidebar.caption("예비 수단: 뉴스 검색으로 번호만 확인")
    min_sources = st.sidebar.slider("뉴스 교차검증 최소 언론사 수", 2, 5, 2)
    if st.sidebar.button("🔎 뉴스 검색으로 새 회차 확인"):
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
    inject_custom_css()
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
