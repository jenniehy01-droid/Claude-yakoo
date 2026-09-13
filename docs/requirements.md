# 야쿠헌터즈 사업성 시뮬레이션 — 요구사항 명세

> 상태: 1차 개발 범위 (외부 API 없이 가상 데이터 파일로 실행되는 버전)
> 본 문서에서 다루는 모든 예시 수치는 **가상(더미) 값**이며, 실제 사업/고객 데이터가
> 아니다. 실사 데이터가 투입되기 전까지 이 시스템의 산출물은 "가상 데이터 기반
> 데모 결과"로만 취급한다.

## 0. 사전 확인 사항

이 리포지토리(`jenniehy01-droid/Claude-yakoo`)와 현재 세션에서 접근 가능한
스킬/플러그인 카탈로그를 조사했으나, 요청에서 언급된 "Harness 100"이나
"financial-modeler"라는 이름의 기존 에이전트·스킬 구조는 발견하지 못했다
(저장소는 커밋이 전혀 없는 빈 저장소였고, 원격에도 아무 브랜치가 없었다).
따라서 아래 역할 구성은 참고할 기존 자산 없이 이번 요청 사양에 맞춰 새로
설계한 것이다.

## 1. 목적

프레시매니저(FM) 기반 고객 유입 프로그램인 **야쿠헌터즈**를 **일반 판촉**과
비교하여, 지역(region) · 운영 규모(FM 투입 수) · 보상 수준(reward level) 조합별로
**추가 손익(증분 이익)**을 비교하고, 파일럿 실적이 들어올 때마다 전환율·재구매율
가정을 갱신하여 손익 추정치를 재계산할 수 있는 시뮬레이션 프로그램을 만든다.

## 2. 용어 정의

| 용어 | 정의 |
|---|---|
| 프레시매니저(FM) | 지역에서 고객을 직접 접촉/모집하는 운영 인력 |
| 야쿠헌터즈 | FM이 특정 리워드(보상) 체계로 신규 고객을 유입시키는 실험 프로그램 (실험군) |
| 일반 판촉 | 기존에 운영 중인 표준 판촉 방식 (비교군/대조군) |
| 실험군(treatment) | 야쿠헌터즈 프로그램이 적용된 고객 접촉 그룹 |
| 비교군(control) | 일반 판촉이 적용된 고객 접촉 그룹 |
| 관광객(tourist) | 국내 배송이 불가능한 1회성 소비 고객 세그먼트 (재구매 미적용) |
| 국내 배송 가능 고객(domestic) | 배송이 가능하여 재구매가 발생할 수 있는 고객 세그먼트 |
| 전환율(conversion rate) | 접촉 고객 중 신규 고객으로 전환된 비율 |
| 재구매율(repeat purchase rate) | 관찰 기간 내 1회 이상 재구매한 국내 고객의 비율 |
| 관찰 기간(observation window) | 전환/재구매 여부를 확정하기 위해 기다려야 하는 최소 경과일 |
| 초기 제작비 | 프로그램 런칭을 위한 1회성 비용(홍보물, 키트 등). 반복 운영비와 분리 표시 |

## 3. 데이터 항목

모든 수치형 입력 값은 다음 4개 메타 항목을 **반드시** 함께 기록한다.

- `value_type`: `실제`(actual, 파일럿/실사 데이터에서 산출) | `추정`(estimate, 유사
  사례·벤치마크에서 추정) | `가정`(assumption, 근거 자료 없이 잠정 설정)
- `source`: 값의 출처 (예: "2026-08 파일럿 대조군 집계", "팀 워크숍 추정")
- `period`: 값이 유효한 기준 기간 (예: "2026-07~2026-08")
- `notes`: 선택, 추가 설명

### 3.1 assumptions (프로그램 전역 가정) — `data/input/assumptions.json`

| key | 설명 | 단위 |
|---|---|---|
| conversion_rate_domestic_treatment | 국내 고객 × 실험군 전환율 | 비율(0~1) |
| conversion_rate_tourist_treatment | 관광객 × 실험군 전환율 | 비율(0~1) |
| conversion_rate_domestic_control | 국내 고객 × 비교군 전환율 | 비율(0~1) |
| conversion_rate_tourist_control | 관광객 × 비교군 전환율 | 비율(0~1) |
| avg_order_value_domestic | 국내 고객 평균 객단가 | 원 |
| avg_order_value_tourist | 관광객 평균 객단가 | 원 |
| repeat_purchase_rate_domestic | 관찰기간 내 1회 이상 재구매한 국내 고객 비율 | 비율(0~1) |
| avg_repeat_orders_per_repeat_customer_domestic | 재구매 고객 1인당 평균 재구매 횟수 | 횟수 |
| regular_promo_cost_per_conversion | 일반 판촉 전환 1건당 비용 | 원 |
| delivery_cost_per_order_domestic | 국내 배송 1건당 배송비 | 원 |
| initial_production_cost_program | 프로그램 런칭 1회성 제작비 (전체) | 원 |
| conversion_observation_window_days | 전환 확정까지 대기 일수 | 일 |
| repeat_purchase_observation_window_days | 재구매 확정까지 대기 일수 | 일 |

### 3.2 reward_levels (보상 수준) — `data/input/reward_levels.csv`

컬럼: `reward_level_id, label, reward_cost_per_conversion, value_type, source, period`

FM에게 신규 전환 1건당 지급하는 보상 금액을 보상 수준(예: 저/중/고)별로 정의한다.

### 3.3 regions (지역 · 운영 규모 파라미터) — `data/input/regions.csv`

컬럼: `region_id, region_name, tourist_share, contacted_customers_per_fm, fixed_operation_cost_per_fm, value_type, source, period`

- `tourist_share`: 해당 지역 접촉 고객 중 관광객 비중
- `contacted_customers_per_fm`: FM 1인이 접촉 가능한 고객 수 (비교군/실험군 동일—
  동일 모집단에 서로 다른 프로그램을 적용한다는 전제)
- `fixed_operation_cost_per_fm`: FM 1인당 고정 운영관리비 (규모 비례)

### 3.4 scenarios (시나리오 정의) — `data/input/scenarios.csv`

컬럼: `scenario_id, region_id, fm_count, reward_level_id, label`

지역 × 운영 규모(FM 투입 수) × 보상 수준의 조합이 하나의 시나리오가 된다.

### 3.5 파일럿 실적 원자료 (customer-level) — `data/input/pilot/*.csv`

**전환 실적 파일** (`pilot_conversion_*.csv`):
`record_id, customer_id, region_id, group(treatment|control), segment(tourist|domestic), contact_date, converted(Y|N), conversion_window_end_date, source_file`

**재구매 실적 파일** (`pilot_repeat_purchase_*.csv`) — domestic 고객만 대상:
`record_id, customer_id, region_id, group(treatment|control), acquisition_date, repeat_orders_count, repeat_window_end_date, source_file`

`as_of_date` (분석 기준일) 기준으로 `*_window_end_date <= as_of_date` 인 레코드만
"관찰 기간이 완료된 고객"으로 간주하여 비율 산출에 사용한다.

## 4. 계산식

세그먼트 s ∈ {tourist, domestic}, 그룹 g ∈ {treatment, control}.

```
contacted(region, g)            = fm_count(region) * contacted_customers_per_fm(region)
contacted_tourist(region, g)    = contacted(region, g) * tourist_share(region)
contacted_domestic(region, g)   = contacted(region, g) * (1 - tourist_share(region))

new_customers(segment, g)       = contacted_segment(region, g) * conversion_rate(segment, g)

revenue_tourist(g)   = new_customers(tourist, g) * avg_order_value_tourist
revenue_domestic(g)  = new_customers(domestic, g) * avg_order_value_domestic
                        * (1 + repeat_purchase_rate_domestic * avg_repeat_orders_per_repeat_customer_domestic)
revenue(g)           = revenue_tourist(g) + revenue_domestic(g)

variable_unit_cost(treatment) = reward_cost_per_conversion(reward_level)
variable_unit_cost(control)   = regular_promo_cost_per_conversion

acquisition_cost(g) = (new_customers(tourist, g) + new_customers(domestic, g)) * variable_unit_cost(g)

delivery_cost(g) = new_customers(domestic, g)
                    * (1 + repeat_purchase_rate_domestic * avg_repeat_orders_per_repeat_customer_domestic)
                    * delivery_cost_per_order_domestic

fixed_cost(region) = fm_count(region) * fixed_operation_cost_per_fm(region)   # 두 그룹 동일 가정

cost_excl_initial(g) = acquisition_cost(g) + delivery_cost(g) + fixed_cost(region)

profit_excl_initial(g) = revenue(g) - cost_excl_initial(g)

# 초기 제작비는 실험군(야쿠헌터즈)에만 1회성으로 발생한다고 가정
profit_incl_initial(treatment) = profit_excl_initial(treatment) - initial_production_cost_program
profit_incl_initial(control)   = profit_excl_initial(control)

incremental_profit_excl_initial = profit_excl_initial(treatment) - profit_excl_initial(control)
incremental_profit_incl_initial = profit_incl_initial(treatment) - profit_incl_initial(control)
```

### 4.1 민감도 분석

지정된 파라미터(전환율, 재구매율, 보상비 등)를 -20%/-10%/기준/+10%/+20%처럼
**결정론적 격자(grid)** 로 흔들어 위 계산식을 재계산한다. 근거 없는 확률분포나
난수 기반 전환율을 생성하지 않는다 (필수 규칙). Monte Carlo류 확률적 시뮬레이션은
1차 개발 범위에 포함하지 않는다.

## 5. 검증 기준 (validation)

1. **필수 메타데이터**: 모든 assumption 값에 `value_type/source/period`가 존재해야 함.
2. **범위 검증**: 모든 비율 값은 [0,1], 모든 금액/개수는 0 이상.
3. **참조 무결성**: scenarios.csv의 `region_id`, `reward_level_id`가 각각
   regions.csv, reward_levels.csv에 존재해야 함.
4. **내부 정합성 재계산**: 저장된 손익 결과를 구성요소(매출-비용)로 재계산했을 때
   부동소수점 오차(1e-6) 이내로 일치해야 함.
5. **세그먼트 합계 검증**: tourist+domestic 접촉 고객 합이 전체 접촉 고객 수와 일치.
6. **파일럿 표본 크기**: 관찰기간 완료 표본이 지정 최소 표본(기본 30건) 미만이면
   "표본 부족" 경고 플래그.
7. **치명적 실패 시 확대 권고 보류**: 1~5 중 하나라도 실패하거나 핵심 입력이
   누락되면 `expansion_recommendation_allowed = False`로 설정하고, 보고서에는
   반드시 "확대 권고 보류" 문구를 명시한다.

## 6. 산출물

각 실행은 `output/run_<timestamp>/` 폴더에 다음을 남긴다.

- `manifest.json`: 계산 프로그램 버전(`CALC_VERSION`), 난수 시드(`RANDOM_SEED`,
  가상 예시 데이터 생성 시에만 사용), 입력 파일 SHA-256 해시, 실행 시각
- `pnl_results.json`: 시나리오별 손익 계산 원자료 (Python 실행 결과)
- `sensitivity_results.json`: 민감도 분석 격자 결과
- `validation_report.json`: 검증 항목별 통과/실패, 확대 권고 가능 여부
- `report_ko.md`: 위 JSON만을 근거로 작성된 한국어 사업성 보고서

## 7. 버전 관리 / 재현성 규칙

- `yakoo_sim.config.CALC_VERSION`: 계산 로직 버전 문자열. 계산식이 바뀌면 증가.
- `yakoo_sim.config.RANDOM_SEED`: 가상 예시 데이터를 생성할 때만 사용하는 고정 시드.
  손익 계산 자체는 완전 결정론적이며 난수를 사용하지 않는다.
- 파일럿 원자료는 `data/ledger/ingested_records.json`에 `customer_id` 기준으로
  적재 이력을 남겨, **동일 파일을 다시 넣어도 동일 고객 레코드가 중복 반영되지
  않도록** 한다 (최신 스냅샷으로 upsert, 합산하지 않음).
- 파일 전체가 이전에 처리된 것과 바이트 단위로 동일하면(SHA-256 일치) 아예
  건너뛴다.

## 8. 제약 사항

- 1차 개발 범위는 **외부 API·실사 DB 연결 없이** `data/input/`의 가상 파일만
  사용한다. 산출물에는 "가상 데이터 기반" 문구를 항상 명시한다.
- 공개 데이터/사내 데이터 연결은 `yakoo_sim/io_loader.py`의 `InputSource`
  인터페이스를 구현하는 별도 모듈로 교체 가능하도록 설계했다 (예:
  `InternalApiInputSource`). 현재는 `DummyFileInputSource`만 구현되어 있으며,
  다른 구현체는 "미연결" 상태임을 코드 주석/에러 메시지로 명시한다.
