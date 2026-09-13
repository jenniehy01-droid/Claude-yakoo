---
name: yakuhunters-simulation
description: 야쿠헌터즈(프레시매니저 기반 고객 유입 프로그램) 사업성 시뮬레이션을 실행하거나, 파일럿 실적을 반영하거나, 결과 보고서를 갱신할 때 사용한다. "야쿠헌터즈", "프레시매니저 사업성", "파일럿 반영" 등을 언급하면 이 스킬을 사용한다.
---

# 야쿠헌터즈 사업성 시뮬레이션

이 스킬은 `docs/requirements.md` 에 정의된 계산식과 `src/yakoo_sim` Python
패키지를 이용해, 프레시매니저 기반 고객 유입 프로그램(야쿠헌터즈)과 일반
판촉을 지역·운영규모·보상수준별로 비교하고, 파일럿 실적으로 가정을 갱신한다.

**1차 개발 범위**: 외부 API·실사 DB 연결 없이 `data/input/` 의 가상(더미)
데이터로만 동작한다. 모든 산출물에는 가상 데이터임을 명시한다.

## 역할 분담 (서브에이전트)

| 역할 | 에이전트 | 설명 |
|---|---|---|
| 수익 분석 | `yakoo-revenue-analyst` | 매출/신규고객수 분석 |
| 비용 분석 | `yakoo-cost-analyst` | 보상비/배송비/고정비/초기제작비 분석 |
| 시나리오 분석 | `yakoo-scenario-analyst` | 지역×규모×보상수준 비교, 민감도 |
| 데이터 검증·갱신 | `yakoo-data-validator` | 입력 검증, 파일럿 실적 반영·중복방지·가정 갱신 (구 기업가치평가 역할 대체) |
| 결과 검증 | `yakoo-results-verifier` | 보고서 작성 전 최종 정합성 확인 |
| 보고서 작성 | `yakoo-report-writer` | 검증된 결과만으로 한국어 보고서 작성 |

## 표준 워크플로

### 1. 베이스라인 실행
```bash
PYTHONPATH=src python3 -m yakoo_sim.cli run --out output/run_<날짜>
```
→ `output/run_<날짜>/` 에 manifest/pnl_results/sensitivity_results/
validation_report/report_ko.md 생성.

### 2. 파일럿 실적 반영 (데이터 검증·갱신 역할)
```bash
PYTHONPATH=src python3 -m yakoo_sim.cli ingest-pilot \
  --conversion-file data/input/pilot/<전환실적>.csv \
  --repeat-file data/input/pilot/<재구매실적>.csv \
  --as-of <기준일 YYYY-MM-DD> \
  --assumptions-in data/input/assumptions.json \
  --assumptions-out data/input/assumptions_after_pilot_<기준일>.json \
  --update-report-out output/pilot_update_<기준일>.json
```
- 같은 파일을 다시 넣어도 `customer_id` 기준 upsert로 중복 반영되지 않는다
  (ledger: `data/ledger/pilot_ledger.json`).
- `--as-of` 이후 시점에는 새 파일 없이 같은 명령을 다시 실행하는 것만으로도,
  그 사이 관찰기간이 완료된 코호트가 자동으로 갱신 대상에 포함된다.
- 표본이 `MIN_PILOT_SAMPLE_SIZE`(기본 30) 미만인 항목은 갱신되지 않고
  경고만 남는다.

### 3. 갱신된 가정으로 재실행
```bash
PYTHONPATH=src python3 -m yakoo_sim.cli run \
  --assumptions data/input/assumptions_after_pilot_<기준일>.json \
  --out output/run_after_pilot_<기준일>
```

### 4. 결과 검증 → 보고서
- `yakoo-results-verifier` 가 `output/run_.../validation_report.json` 확인.
- 문제 없으면 `yakoo-report-writer` 가 `report_ko.md` 를 최종 보고서로 확정.
- `expansion_recommendation_allowed=false` 이면 확대 권고 문구를 넣지 않는다.

### 5. 파일럿 전/후 비교
```bash
python3 scripts/compare_pilot_impact.py
```
→ `output/pilot_impact_comparison.md` 에 베이스라인/파일럿반영 손익·가정
변화 비교표 생성 (모두 기존 run들의 JSON 값을 그대로 인용).

## 필수 규칙 (모든 역할 공통)
- 모든 수치는 실제값·추정값·가정을 구분하고 출처·기준기간을 기록한다.
- 실제 데이터/API 연결이 없으면 연결된 것처럼 설명하지 않는다.
- 손익 숫자는 `yakoo_sim` Python 실행 결과만 사용한다 (직접 암산 금지).
- 일반 판촉 대비 추가 이익과, 초기 제작비 포함/제외 손익을 항상 함께 표시한다.
- 근거 없는 확률/전환율을 자동으로 만들지 않는다 (민감도는 결정론적 격자만).
- 관광객/국내 배송 가능 고객, 비교군/실험군을 항상 구분한다.
- 입력 데이터, 가정, 계산 프로그램 버전(`CALC_VERSION`), 난수 시드
  (`RANDOM_SEED`)를 항상 산출물에 기록한다.
- 중요한 입력 누락이나 계산 검증 실패 시 확대 권고를 보류한다.
- 같은 파일을 다시 넣어도 실적이 중복 반영되지 않게 한다 (ledger upsert).
