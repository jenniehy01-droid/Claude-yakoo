"""야쿠헌터즈 사업성 시뮬레이션 계산 엔진.

이 패키지는 외부 API나 실사 데이터 연결 없이, data/input/ 아래의
가상(더미) 입력 파일만으로 동작하도록 설계되었다. 공개 데이터/사내
데이터 연결은 ``io_loader.InputSource`` 인터페이스를 구현하는
별도 모듈로 교체하면 되도록 분리해 두었다 (1차 개발 범위에는 포함하지 않음).
"""

from .config import CALC_VERSION, RANDOM_SEED

__all__ = ["CALC_VERSION", "RANDOM_SEED"]
