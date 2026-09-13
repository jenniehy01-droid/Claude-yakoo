# 파일럿 데이터 반영 전/후 손익 변화 재현 결과

> 아래 수치는 모두 각 실행 시점의 `output/run_*/pnl_results.json` (Python 실행 결과)에서 그대로 가져온 값입니다.

## 베이스라인 (파일럿 반영 전)
- assumptions_version: `assumptions.json@2026-08-31`
- as_of_date: `2026-08-31`

## 파일럿 1차 반영 (as_of 2026-09-01)
- assumptions_version: `assumptions_after_pilot_2026-09-01.json@2026-09-01`
- as_of_date: `2026-09-01`

## 파일럿 2차 반영 (as_of 2026-12-01, 신규 파일 없이 재계산)
- assumptions_version: `assumptions_after_pilot_2026-12-01.json@2026-12-01`
- as_of_date: `2026-12-01`

## 시나리오별 증분이익(초기비용 제외) 비교

| 시나리오 | 베이스라인 (파일럿 반영 전) | 파일럿 1차 반영 (as_of 2026-09-01) | 파일럿 2차 반영 (as_of 2026-12-01, 신규 파일 없이 재계산) |
|---|---:|---:|---:|
| 제주 소규모-저보상 | 1,208,313원 | 920,513원 | 683,077원 |
| 제주 소규모-중보상 | 989,613원 | 683,819원 | 453,846원 |
| 제주 중규모-중보상 | 1,979,226원 | 1,367,639원 | 907,692원 |
| 제주 대규모-고보상 | 2,792,052원 | 1,472,913원 | 592,820원 |
| 서울 소규모-중보상 | 1,683,253원 | 1,596,304원 | 1,485,470원 |
| 서울 중규모-고보상 | 2,469,506원 | 2,222,641원 | 2,001,709원 |
| 부산 소규모-저보상 | 1,584,842원 | 1,435,648원 | 1,279,005원 |
| 부산 중규모-중보상 | 2,627,585원 | 2,284,933원 | 1,978,009원 |

## 가정값 변화 요약 (파일럿 반영으로 갱신된 항목)

### 파일럿 1차 반영 (as_of 2026-09-01)

| 가정 항목 | 이전 값 | 갱신 값 | 표본크기 |
|---|---:|---:|---:|
| conversion_rate_tourist_treatment | 0.09 | 0.0976 | 82 |
| conversion_rate_tourist_control | 0.05 | 0.0899 | 89 |
| conversion_rate_domestic_treatment | 0.16 | 0.1730 | 185 |
| conversion_rate_domestic_control | 0.1 | 0.1117 | 179 |

경고(표본 부족 등으로 갱신 보류):
- repeat_purchase_rate_domestic: 표본 부족(n=28 < 30) — 기존 가정 유지, 참고용으로만 기록
- avg_repeat_orders_per_repeat_customer_domestic: 표본 부족(n=5 < 30) — 기존 가정 유지, 참고용으로만 기록

### 파일럿 2차 반영 (as_of 2026-12-01, 신규 파일 없이 재계산)

| 가정 항목 | 이전 값 | 갱신 값 | 표본크기 |
|---|---:|---:|---:|
| conversion_rate_tourist_treatment | 0.09 | 0.0889 | 90 |
| conversion_rate_tourist_control | 0.05 | 0.1042 | 96 |
| conversion_rate_domestic_treatment | 0.16 | 0.1744 | 195 |
| conversion_rate_domestic_control | 0.1 | 0.1111 | 189 |
| repeat_purchase_rate_domestic | 0.22 | 0.1818 | 55 |

경고(표본 부족 등으로 갱신 보류):
- avg_repeat_orders_per_repeat_customer_domestic: 표본 부족(n=10 < 30) — 기존 가정 유지, 참고용으로만 기록
