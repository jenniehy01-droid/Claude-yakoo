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

## 로컬 대시보드 — 파일럿 투자 의사결정 화면

`dashboard/app.py` 는 위 계산 엔진을 **직접 호출**하는 Flask 기반 로컬 웹
대시보드다. 첫 화면은 **"파일럿을 승인할 것인가, 승인한다면 어느 규모로
할 것인가"** 라는 결정을 중심으로 구성했다. 손익 계산식은 화면 코드에 전혀
다시 구현하지 않았고, 아래 검증된(pytest 통과) 함수만 그대로 불러와 쓴다:
`calculator.compute_scenario_pnl / incremental_revenue / incremental_cost /
incremental_new_customers / compute_incremental_cac`,
`scenarios.compute_scenario_bands / run_full_sensitivity / rank_drivers_by_swing`,
`breakeven.solve_breakeven_*`, `decision_inputs.*`, `pilot_update.*`,
`validation.validate_assumptions`.

```bash
pip install -r dashboard/requirements-dashboard.txt
PYTHONPATH=src python3 dashboard/app.py
# 브라우저에서 http://127.0.0.1:5050 접속
```

### 탭 ① 파일럿 투자 의사결정 (첫 화면)

정보를 결정 순서대로 배치했다.

1. **이번에 결정할 사항** — "파일럿 승인 여부와 실행 규모"를 최상단에 두고,
   "사업 확대 여부"는 *지금 결정이 아닌* 별도 결정으로 분리해 표시한다.
   근거가 부족하면 이 자리에서 바로 "투자 추천 보류"를 알린다.
2. **실행안 비교** — 일반 판촉 유지 / 작은 규모 파일럿 / 큰 규모 파일럿을
   나란히 비교한다. 항목은 대상 고객 수, 추가 프로그램 비용, 추가 신규구매자,
   추가 손익(초기 제작비 제외·포함 모두). 필요한 입력이 없으면 그 칸에
   **입력 필요**로 표시한다. 아래 그래프는 실행안 × 보수·중간·낙관 가정의
   추가 손익을 막대 값과 함께 보여준다.
3. **판단을 바꾸는 조건** — 첫 구매율·재구매율·보상비 각각에 대해 추가 손익이
   0이 되는 손익분기점과 현재 가정과의 차이를 계산한다(결정론적 이분법).
   그 값만으로는 손익분기에 닿지 않으면 억지 숫자를 만들지 않고 이유를 밝히며,
   "항상 손실"과 "항상 이익"을 구분해 표시한다. 보수 가정 결과는 추정치임을
   명시하고 **'최대손실'·'확정 손실'로 표현하지 않는다.**
4. **승인 전에 필요한 근거** — 실제 제품 마진, 운영 견적, 허용 손실 한도,
   매니저 처리 여력, 실험 표본 설계의 확보 상태를 표시한다. 하나라도
   확보되지 않으면 **투자 추천을 확정하지 않고**, 무엇이 채워져야 다음
   단계로 갈 수 있는지 명시한다. 상태는 `data/input/decision_readiness.csv`
   에서 읽으므로 근거가 생기면 파일만 갱신하면 된다.
5. **파일럿 후 확대 판단** — 일반 판촉 대비 추가 구매, 30일 재구매, 실제 비용,
   기존 배송 영향에 대해 사전 기준(`data/input/expansion_criteria.csv`)과
   실적을 비교한다. 측정 가능한 지표는 파일럿 원자료에서 자동 산출하고,
   나머지는 "미측정"으로 남긴다.

### 탭 ② 가정 · 계산 근거

세부 입력(관광객 전환율, 객단가, 배송비, 초기 제작비 등)과 계산식, 손익에
가장 큰 영향을 주는 변수 TOP 3, 상세 KPI를 여기에 모았다. 첫 화면은 결정과
실행안 비교에만 집중하도록 분리한 것이다.

### 탭 ③ 파일럿 실적 비교

전환/재구매 실적 CSV를 업로드하면(같은 파일을 다시 올려도 고객 단위로 중복
반영되지 않음) 예상(사전 가정) vs 실적(파일럿)을 비교하고, 그에 따른 추가
손익 변화와 ①탭 ⑤의 확대 기준 판정을 갱신한다.

### 설계 원칙 반영

- **실제값 · 가정 · 가상 예제 구분**: 모든 값에 `실제 / 추정 / 가정 /
  미확보 / 입력필요` 배지를 붙이고, 화면에서 직접 고친 값은
  "가정(대시보드 수정)"으로 따로 표시한다. 상단에는 항상 "가상 예제 데이터"와
  "실 데이터 미연결"을 표시한다.
- **가정만으로 계산한 결과를 "사업성 검증 완료"로 표현하지 않는다.**
- **재계산 필요 표시**: 계산 후 입력을 하나라도 바꾸면 결과 영역이 흐려지고
  "입력이 변경되었습니다" 배너가 뜬다. 다시 "결과 계산"을 눌러야 갱신된다.
- **금액 단위**: 큰 손익은 만원, 단가성 수치(CAC 등)는 원으로 표시하고
  불필요한 소수점은 없앤다. 이익·손실은 색상뿐 아니라 부호(+/−)와
  "이익"/"손실" 문구로 함께 구분한다.
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
갱신까지 실제 브라우저 인터랙션으로 검증했다. 첫 화면은 처음 보는 사람이
아래 세 질문에 답할 수 있는지를 기준으로 점검했다.

| 질문 | 답이 나오는 위치 |
|---|---|
| 지금 무엇을 결정해야 하는가? | ① 이번에 결정할 사항 (승인/규모 vs 확대 분리) |
| 선택안마다 비용과 기대 성과가 어떻게 다른가? | ② 실행안 비교 표와 그래프 |
| 어떤 근거가 확보되면 다음 단계로 갈 수 있는가? | ④ 승인 전에 필요한 근거, ⑤ 확대 기준 |

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
