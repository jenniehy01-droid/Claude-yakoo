# 야쿠헌터즈 사업성 시뮬레이션 Agent

프레시매니저(FM) 기반 고객 유입 프로그램 **야쿠헌터즈**를 **일반 판촉**과
비교하여, 지역 · 운영 규모 · 보상 수준별 추가 손익(증분이익)을 계산하고,
파일럿 실적으로 전환율·재구매율 가정을 갱신하는 시뮬레이션 프로그램이다.

> ⚠️ **가상(더미) 데이터 안내**: 이 저장소의 `data/input/` 아래 모든 예시
> 데이터와 `output/`의 모든 실행 결과는 시연용 가상 데이터로 만든 것이며
> **실제 사업/고객 데이터가 아니다**. 외부 API나 사내 DB에 연결되어 있지
> 않다.

## 개발 경위 메모

요청에서 언급된 "Harness 100의 financial-modeler"라는 기존 에이전트/스킬
구조는 이 저장소(및 접근 가능한 스킬·플러그인 카탈로그)에서 확인되지
않았다 — 저장소는 커밋이 전혀 없는 빈 상태였다. 따라서 아래 6개 역할
구성을 요청 사양에 맞춰 새로 설계했다. 기존에 있었다고 언급된
"기업가치 평가" 역할은 요청대로 **데이터 검증·갱신** 역할로 대체했다.

## 폴더 구조

```
docs/requirements.md          요구사항/데이터항목/계산식/검증기준 명세
data/input/                   가상 입력 데이터 (assumptions, regions, scenarios, pilot 원자료)
data/ledger/                  파일럿 원자료 적재 이력 (중복 방지용, customer_id 기준 upsert)
src/yakoo_sim/                계산 엔진 Python 패키지
  config.py                     버전/난수시드 상수
  models.py                     데이터 모델 (dataclass)
  io_loader.py                  교체 가능한 입력 모듈 인터페이스 (현재 더미 파일 구현체만 존재)
  calculator.py                 손익 계산 (결정론적, 난수 미사용)
  scenarios.py                  시나리오 비교 + 민감도(결정론적 격자) 분석
  pilot_update.py               파일럿 실적 적재(중복방지) + 관찰기간 완료 고객 기준 가정 갱신
  validation.py                 입력/결과 검증 (실패 시 확대 권고 보류)
  report.py                     검증된 JSON만 읽어 한국어 보고서 작성
  cli.py                        실행 진입점
scripts/                       예제 데이터 생성, 파일럿 전/후 비교 스크립트
dashboard/                     로컬 대시보드 (Flask, 계산 엔진 직접 호출)
tests/                         pytest 단위 테스트
output/                        실행 결과 (manifest/손익/민감도/검증/보고서)
.claude/agents/                역할별 서브에이전트 정의
.claude/skills/yakuhunters-simulation/SKILL.md   오케스트레이션 스킬
```

## 빠른 시작

```bash
# 1) 의존성: 표준 라이브러리만 사용 (pandas/numpy 등 외부 패키지 불필요)
#    테스트 실행에는 pytest 만 필요: pip install pytest

# 2) 베이스라인 시나리오 실행 (파일럿 반영 전)
PYTHONPATH=src python3 -m yakoo_sim.cli run --out output/run_baseline

# 3) 결과 확인
cat output/run_baseline/report_ko.md

# 4) 단위 테스트
python3 -m pytest tests/ -q
```

## 파일럿 실적 반영 재현 (핵심 시나리오)

이 저장소에는 아래 시연이 이미 실행되어 `output/`에 결과가 커밋되어 있다.
동일 절차를 다시 실행해도 같은 결과가 재현된다 (계산은 완전 결정론적).

```bash
# (a) 2026-09-01 기준으로 파일럿 전환/재구매 원자료 반영
PYTHONPATH=src python3 -m yakoo_sim.cli ingest-pilot \
  --conversion-file data/input/pilot/pilot_conversion_2026q2.csv data/input/pilot/pilot_conversion_2026q3.csv \
  --repeat-file data/input/pilot/pilot_repeat_purchase_2026q2.csv data/input/pilot/pilot_repeat_purchase_2026q3.csv \
  --as-of 2026-09-01 \
  --assumptions-in data/input/assumptions.json \
  --assumptions-out data/input/assumptions_after_pilot_2026-09-01.json \
  --update-report-out output/pilot_update_2026-09-01.json

# (b) 갱신된 가정으로 재실행
PYTHONPATH=src python3 -m yakoo_sim.cli run \
  --assumptions data/input/assumptions_after_pilot_2026-09-01.json \
  --out output/run_after_pilot_2026-09-01

# (c) 동일 파일을 다시 넣어도 중복 반영되지 않음을 확인 (rows_new=0, rows_updated=0)
PYTHONPATH=src python3 -m yakoo_sim.cli ingest-pilot \
  --conversion-file data/input/pilot/pilot_conversion_2026q2.csv data/input/pilot/pilot_conversion_2026q3.csv \
  --repeat-file data/input/pilot/pilot_repeat_purchase_2026q2.csv data/input/pilot/pilot_repeat_purchase_2026q3.csv \
  --as-of 2026-09-01 \
  --assumptions-in data/input/assumptions.json \
  --assumptions-out /tmp/reingest_check.json

# (d) 새 파일 없이 기준일만 2026-12-01로 미루면, 그 사이 관찰기간이 끝난
#     코호트(특히 재구매율 90일 관찰기간)가 자동으로 갱신에 포함된다
PYTHONPATH=src python3 -m yakoo_sim.cli ingest-pilot \
  --as-of 2026-12-01 \
  --assumptions-in data/input/assumptions.json \
  --assumptions-out data/input/assumptions_after_pilot_2026-12-01.json \
  --update-report-out output/pilot_update_2026-12-01.json

PYTHONPATH=src python3 -m yakoo_sim.cli run \
  --assumptions data/input/assumptions_after_pilot_2026-12-01.json \
  --out output/run_after_pilot_2026-12-01

# (e) 세 실행 결과 비교표 생성
python3 scripts/compare_pilot_impact.py
cat output/pilot_impact_comparison.md
```

`output/pilot_impact_comparison.md` 에서 확인할 수 있듯,
- 1차 파일럿 반영(2026-09-01) 시점에는 전환율만 갱신되고 재구매율은 표본
  부족(n=28<30)으로 기존 가정이 유지된다.
- 2차 시점(2026-12-01, **신규 파일 투입 없이** 동일 ledger로 재계산)에는
  재구매율 표본이 55건으로 늘어 갱신되며, 증분이익이 다시 변한다.
- 모든 시나리오의 증분이익(초기비용 제외)이 파일럿 반영 후 하향 조정된다
  (초기 가정이 파일럿 실측 전환율보다 낙관적이었기 때문 — 예제 데이터에서
  의도적으로 재현한 상황).

## 로컬 대시보드 — MBA 발표용 화면

`dashboard/app.py` 는 위 계산 엔진을 **직접 호출**하는 Flask 기반 로컬 웹
대시보드다. 비개발자가 "이 조건으로 야쿠헌터즈를 운영하면 얼마가 남고,
어떤 조건을 개선해야 하는가"를 한 화면에서 바로 파악할 수 있도록 설계했다.
손익 계산식은 화면 코드에 전혀 다시 구현하지 않았고, 아래 검증된(pytest
통과) 계산기 함수만 그대로 불러와 쓴다:
`yakoo_sim.calculator.compute_scenario_pnl / incremental_revenue / compute_incremental_cac`,
`yakoo_sim.scenarios.compute_scenario_bands / run_full_sensitivity / rank_drivers_by_swing`,
`yakoo_sim.validation.validate_assumptions`, `yakoo_sim.pilot_update.*`.

```bash
pip install -r dashboard/requirements-dashboard.txt
PYTHONPATH=src python3 dashboard/app.py
# 브라우저에서 http://127.0.0.1:5050 접속
```

### 화면 구성

1. **상단**: 제목, 데이터 기준일, "가상 데이터" / "실 데이터 미연결" 표시.
2. **왼쪽 입력**: 지역, 참여 인원(FM 수), 첫 구매율, 재구매율, 보상비 —
   비율 입력에는 분모 설명을 함께 표시한다. 세부 비용(관광객 첫구매율,
   일반판촉 비교기준, 객단가, 배송비, 초기 제작비 등)은 "상세 설정"으로
   접어 두었다.
3. **중앙 상단 KPI 카드 4개**: 추가 매출, 초기 제작비 제외/포함 추가 손익,
   증분 CAC(고객 1명 추가 획득 비용). 이익·손실은 색상뿐 아니라 부호(+/−)와
   "이익"/"손실" 문구로 함께 구분한다.
4. **중앙 그래프**: 일반판촉 vs 야쿠헌터즈를 보수·중간·낙관 3개 시나리오
   밴드(핵심 수요 가정 ±20%, 결정론적 격자)로 비교한다.
5. **하단**: 손익에 가장 큰 영향을 주는 변수 TOP 3(민감도 swing 기준)와
   이번 계산에 사용한 주요 가정(실제/추정/가정 구분 배지 포함)을 보여준다.
6. **파일럿 실적 비교 탭**: 전환/재구매 실적 CSV를 업로드하면(같은 파일을
   다시 올려도 고객 단위로 중복 반영되지 않음) 예상(사전 가정) vs 실적
   (파일럿) 전환율·재구매율과, 그에 따른 손익 변화를 시뮬레이터 탭의 현재
   지역·인원·보상비 조건 기준으로 비교해 보여준다.

### 설계 원칙 반영

- **탐색적 입력 vs 검증된 값 구분**: 화면에서 값을 기준 파일과 다르게
  입력하면 "가정(대시보드 수정)"으로 명확히 표시하고, "이 결과는 사업성
  검증 완료가 아니며 확대 권고 근거로 사용할 수 없다"고 항상 경고한다.
  가정만으로 계산한 결과를 "사업성 검증 완료"로 표현하지 않는다.
- **재계산 필요 표시**: 계산 실행 후 왼쪽 입력값을 하나라도 바꾸면, 결과
  영역이 즉시 흐려지고(투명도 감소) "입력이 변경되었습니다 — 재계산이
  필요합니다" 배너가 뜬다. 다시 "계산 실행"을 눌러야 새 결과로 갱신된다 —
  이전 입력의 결과를 새 입력값과 혼동하지 않도록 하기 위함.
- **금액 단위**: 큰 손익 수치는 만원 단위로, 단가성 수치(CAC 등)는 원 단위로
  표시하고 불필요한 소수점은 없앤다.
- 밝은 배경 + 짙은 녹색(#0f5132)을 주 색상으로 사용했다.

로컬 전용이며, 외부 인터넷 연결 없이 완전히 오프라인으로 동작한다 (그래프도
서버에서 이미지로 그려서 내려주므로 브라우저의 외부 접속이 필요 없다).
그래프에 한글이 깨져 보이면(네모(□)로 표시) 한글 폰트가 설치돼 있지 않은
것이므로, Linux는 `sudo apt install fonts-nanum`, macOS/Windows는 보통 기본
한글 폰트가 있어 별도 설치가 필요 없다.

### 실제 화면 검증

Playwright(헤드리스 Chromium)로 실제 서버를 구동해 데스크톱(1400px)과
모바일(420px) 폭에서 스크린샷을 찍어 숫자 잘림·그래프 겹침·가로 스크롤이
없는지 확인했고, 입력값 변경 → "재계산 필요" 배너 표시 → 재실행 → 결과
갱신까지 실제 브라우저 인터랙션으로 검증했다.

## 데이터 검증 및 확대 권고 보류 규칙

`output/run_*/validation_report.json` 의 `expansion_recommendation_allowed` 가
`false` 이면, 보고서(`report_ko.md`)는 자동으로 "확대 권고 보류" 문구를
최상단에 표시한다. 검증 규칙 목록은 `docs/requirements.md` 5절 참고.

## 공개/사내 데이터 연결로 교체하는 방법

`src/yakoo_sim/io_loader.py` 의 `InputSource` 추상 클래스를 구현하는 새
클래스를 추가하면 된다 (`DummyFileInputSource` 참고). 1차 개발 범위에는
포함되지 않으며, `UnconnectedInputSource` 는 호출 시 명확한
`NotImplementedError` 를 발생시켜 "연결된 것처럼" 동작하지 않는다.

## Claude Code 에이전트/스킬

`.claude/skills/yakuhunters-simulation/SKILL.md` 가 전체 워크플로를
오케스트레이션하며, 아래 6개 역할로 구성된다 (요청에 따라 기존
"기업가치 평가" 역할은 "데이터 검증·갱신"으로 대체됨):

- `yakoo-revenue-analyst` — 수익 분석
- `yakoo-cost-analyst` — 비용 분석
- `yakoo-scenario-analyst` — 시나리오·민감도 분석
- `yakoo-data-validator` — 데이터 검증·갱신 (파일럿 반영/중복방지 포함)
- `yakoo-results-verifier` — 결과 검증 (보고서 작성 전 최종 관문)
- `yakoo-report-writer` — 한국어 결과 보고서 작성

## 완료 기준 매핑

| 완료 기준 | 위치 |
|---|---|
| 예제 실행 명령 | 본 README "빠른 시작" / "파일럿 실적 반영 재현" |
| 입력 양식 | `data/input/*.json`, `*.csv` + `docs/requirements.md` 3절 |
| 계산 프로그램 | `src/yakoo_sim/*.py` (테스트: `tests/`) |
| 핵심 검증 결과 | `output/run_*/validation_report.json`, `tests/test_validation.py` |
| 한국어 결과 보고서 | `output/run_*/report_ko.md` |
| 파일럿 반영 전/후 재현성 | `output/pilot_impact_comparison.md`, `output/pilot_update_*.json` |
