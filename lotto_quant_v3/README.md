# LOTTO 6/45 QUANT V3

한국 로또 6/45 데이터 기반 확률·통계·포트폴리오 분석 툴킷 + Streamlit 대시보드.

## 설치

```bash
pip install -r requirements.txt
```

가상환경을 쓰려면:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 실행

전체 파이프라인 (데이터 수집 → 확률 검증 → 포트폴리오 생성 → 백테스트):

```bash
python -m lotto_quant_v3.main
```

옵션:

```bash
python -m lotto_quant_v3.main --rounds 200        # 최근 200회차 수집
python -m lotto_quant_v3.main --skip-fetch         # 기존 DB 재사용, 재수집 생략
```

대시보드 (통계/포트폴리오/백테스트/**추첨 플레이 모드** 포함):

```bash
streamlit run lotto_quant_v3/dashboard/app.py
```

테스트:

```bash
python -m unittest lotto_quant_v3.tests.test_core -v
```

## 데이터 출처에 대한 중요 안내

동행복권(dhlottery.co.kr) 공식 JSON API(`common.do?method=getLottoNumber`)는
2026년 1월 사이트 개편 이후 curl / 실제 브라우저 양쪽 모두에서 홈페이지로
302 리다이렉트되어 더 이상 동작하지 않는 것으로 확인되었습니다 (봇 탐지 우회는
시도하지 않았습니다).

**기준 데이터 (1~1236회):** 사용자가 제공한 엑셀(`회차별 당첨번호_*.xlsx`)을
`data/excel_import.py`로 가져와 DB의 기준 이력으로 사용합니다. 겹치는 300개
회차를 자체 스크래핑 데이터와 대조한 결과 불일치 0건이었습니다.

**신규 회차 자동 수집 (1237회~):** `data/news_search.py`가 Google 뉴스 검색
(API 키 불필요, `news.google.com/rss/search`)으로 회차별 기사 제목에서 당첨번호를
파싱하고, **서로 다른 언론사 2곳 이상이 동일한 번호를 보도해야만** 저장합니다
(불일치 시 저장하지 않고 건너뜀). 대시보드 사이드바의 "🔎 새 회차 확인" 버튼이나
`python -m lotto_quant_v3.main`을 실행하면 자동으로 확인합니다. 실제 1231~1236회에
대해 테스트한 결과 최대 18개 언론사가 동일 번호에 합의했고, 엑셀 기준 데이터와
100% 일치했습니다.

이전에 쓰던 [lottolyzer.com](https://en.lottolyzer.com) / [pyony.com](https://pyony.com)
스크래퍼는 `data/collector.py`에 백업 방식으로 남아있습니다 (더 이상 기본 경로는 아님).

## 모듈 구성

| 모듈 | 역할 |
|---|---|
| `probability/engine.py` | C(45,6) 및 1~5등 확률 정확 계산 |
| `data/excel_import.py` | 사용자 제공 1~1236회 엑셀 이력 적재 |
| `data/news_search.py` | Google 뉴스 검색으로 신규 회차 자동 발견 (언론사 2곳+ 합의 필요) |
| `data/collector.py`, `data/db.py` | (백업) lottolyzer/pyony 스크래핑 교차검증 + SQLite 저장 |
| `statistics/analysis.py` | 빈도, 미출현 회차, 번호쌍 동시출현, 합계분포 |
| `statistics/significance.py` | Paired t-test / Wilcoxon 유의성 검정 |
| `portfolio/generator.py` | 5게임 생성 (내부/게임간 중복 없음) |
| `portfolio/probability.py` | 포트폴리오 정확 당첨확률 (C(45,6) 전수조사, 단순 독립사건 공식 아님) |
| `optimization/optimizer.py` | 번호 커버리지 분산 최적화 (예측이 아닌 분산) |
| `simulation/monte_carlo.py` | 최대 100만 회 몬테카를로 시뮬레이션 |
| `backtest/walkforward.py` | Walk-forward 백테스트 (미래 데이터 누출 방지 assert 포함) |
| `dashboard/app.py` | Streamlit 대시보드 + 🎰 추첨 플레이 모드 |

## 알려진 한계

- Walk-forward 백테스트 결과, 빈도 가중 포트폴리오(V3)는 랜덤 baseline 대비
  통계적으로 유의한 우위가 없습니다 (p≈0.32). 이는 로또 추첨이 균등분포
  독립시행이라는 사실과 일치하는 정상적인 결과이며, "당첨 예측"이 아닌
  "번호 분산/포트폴리오 관리" 도구로 이 프로젝트를 이해해야 합니다.
- 데이터 소스가 공식 API가 아닌 서드파티 사이트이므로, 해당 사이트의 구조가
  바뀌면 `data/collector.py`의 파서가 깨질 수 있습니다.
