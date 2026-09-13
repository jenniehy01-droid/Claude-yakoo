"""버전 및 재현성 관련 상수.

CALC_VERSION 은 계산 로직(수식)이 바뀔 때마다 올린다.
RANDOM_SEED 는 "가상 예시 데이터 생성"에만 사용하는 고정 시드다.
손익 계산 엔진(calculator.py) 자체는 난수를 전혀 사용하지 않는다 —
근거 없는 확률/전환율을 자동으로 만들지 않는다는 필수 규칙에 따른 것이다.
"""

CALC_VERSION = "0.1.0"
RANDOM_SEED = 20260901

# 검증 기준: 파일럿 표본이 이 값보다 적으면 "표본 부족" 경고
MIN_PILOT_SAMPLE_SIZE = 30

# 부동소수점 재계산 검증 허용 오차
RECONCILIATION_TOLERANCE = 1e-6
