"""LOTTO 6/45 QUANT V3 -- CLI pipeline entrypoint.

Usage (from the project root, i.e. the folder containing lotto_quant_v3/):
    python -m lotto_quant_v3.main
    python -m lotto_quant_v3.main --excel "path/to/회차별 당첨번호.xlsx"  # one-time bootstrap
    python -m lotto_quant_v3.main --skip-fetch                          # reuse existing DB only
    streamlit run lotto_quant_v3/dashboard/app.py   # interactive dashboard + play mode
"""
import argparse
import sys

# Windows consoles often default to a legacy codepage (e.g. cp949) that
# can't encode arbitrary Unicode punctuation printed by this pipeline.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from lotto_quant_v3.backtest import walkforward
from lotto_quant_v3.data import db, excel_import, news_search
from lotto_quant_v3.optimization import optimizer
from lotto_quant_v3.portfolio import probability
from lotto_quant_v3.probability import engine as prob_engine
from lotto_quant_v3.statistics import analysis, significance


def run_pipeline(excel_path: str | None, skip_fetch: bool, min_history: int, news_min_sources: int):
    print("=" * 60)
    print("LOTTO 6/45 QUANT V3 - PIPELINE")
    print("=" * 60)

    db.init_db()
    if excel_path:
        print(f"\n[1/5] 엑셀 기준 데이터 적재: {excel_path}")
        bootstrap = excel_import.import_excel(excel_path)
        for d in bootstrap:
            db.upsert_draw(d.round, d.draw_date, list(d.numbers), d.bonus,
                            source="user_excel_import", verified=True)
        print(f"  -> {len(bootstrap)}개 회차 적재 완료 (회차 {bootstrap[0].round}~{bootstrap[-1].round})")
    elif not skip_fetch:
        latest = db.get_latest_round() or 0
        print(f"\n[1/5] 신규 회차 확인 (Google 뉴스 검색, 언론사 {news_min_sources}곳 이상 일치 필요)...")
        new_draws = news_search.discover_new_rounds(latest, min_sources=news_min_sources)
        for d in new_draws:
            db.upsert_draw(d.round, d.draw_date, list(d.numbers), d.bonus,
                            source=f"google_news_search(min_sources={news_min_sources})", verified=True)
        print(f"  -> 신규 {len(new_draws)}개 회차 저장 (뉴스 교차검증 통과)" if new_draws
              else "  -> 신규 회차 없음")
    draws = db.get_all_draws()
    print(f"  DB 보유 회차: {len(draws)} (최신: {db.get_latest_round()})")

    print("\n[2/5] 확률 엔진 검증...")
    summary = prob_engine.summarize()
    assert summary["total_combinations"] == 8_145_060
    print(f"  C(45,6) = {summary['total_combinations']:,} (검증됨)")
    for tier, info in summary["tiers"].items():
        print(f"  {tier}등: 1/{info['odds_1_in']:.1f}")

    print("\n[3/5] 포트폴리오 생성 (분산 최적화, 5게임)...")
    df = analysis.draws_to_frame(draws)
    weights = (analysis.number_frequency(df).values + 1).astype(float)
    tickets = optimizer.optimize_portfolio(weights=weights, seed=42)
    for i, t in enumerate(tickets, 1):
        print(f"  게임 {i}: {t}")

    print("\n[4/5] 포트폴리오 정확 확률 (전수조사)...")
    exact = probability.exact_portfolio_distribution(tickets)
    print(f"  1등 확률: {exact['jackpot_ways']}/{exact['total_draws']:,} = {exact['jackpot_probability']:.10f}")
    print(f"  P(>=3개 일치) = {exact['exact_probability_at_least'][3]:.6f}")

    print(f"\n[5/5] Walk-forward 백테스트 (min_history={min_history}, 데이터 누출 없음)...")
    if len(draws) >= min_history + 10:
        bt = walkforward.walk_forward_backtest(draws, min_history=min_history, seed=7)
        sig = significance.compare_strategies(bt["v3_hits_by_round"], bt["baseline_hits_by_round"])
        print(f"  테스트 회차 수: {bt['n_tested_rounds']}")
        print(f"  V3 평균 최고 적중: {bt['v3_mean_best_match']:.3f} | "
              f"랜덤 baseline: {bt['baseline_mean_best_match']:.3f}")
        print(f"  유의성 검정 p-value: {sig['paired_ttest']['p_value']:.4f} -> {sig['interpretation']}")
    else:
        print("  건너뜀 (히스토리 부족)")

    print("\n완료. 대시보드: streamlit run lotto_quant_v3/dashboard/app.py")


def main():
    parser = argparse.ArgumentParser(description="LOTTO 6/45 QUANT V3 pipeline")
    parser.add_argument("--excel", type=str, default=None,
                         help="1회차부터의 기준 이력 엑셀 파일 경로 (최초 1회 부트스트랩용)")
    parser.add_argument("--skip-fetch", action="store_true", help="신규 회차 뉴스 검색 생략, 기존 DB만 사용")
    parser.add_argument("--news-min-sources", type=int, default=2,
                         help="신규 회차 확정에 필요한 최소 독립 언론사 수")
    parser.add_argument("--min-history", type=int, default=52, help="백테스트 최소 학습 회차 수")
    args = parser.parse_args()
    run_pipeline(args.excel, args.skip_fetch, args.min_history, args.news_min_sources)


if __name__ == "__main__":
    main()
