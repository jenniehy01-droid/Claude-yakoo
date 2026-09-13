"""입력 데이터 로더 — 교체 가능한 입력 모듈 인터페이스.

1차 개발 범위는 `DummyFileInputSource` (로컬 가상 파일)만 구현한다.
공개 데이터/사내 데이터 API 연결은 이 `InputSource` 인터페이스를 구현하는
별도 클래스를 추가하는 방식으로 확장하도록 설계했다. 아직 그런 구현체는
없으므로, 연결된 것처럼 보이는 코드/문서를 두지 않는다 — 시도 시
`NotImplementedError`로 명확히 실패한다.
"""
from __future__ import annotations

import csv
import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .models import Assumption, RewardLevel, Region, Scenario


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class InputSource(ABC):
    """입력 데이터 소스 인터페이스. 실사 연결 시 이 클래스를 구현한다."""

    @abstractmethod
    def load_assumptions(self) -> tuple[dict[str, Assumption], str]:
        """(key -> Assumption, as_of_date) 반환."""

    @abstractmethod
    def load_reward_levels(self) -> dict[str, RewardLevel]:
        ...

    @abstractmethod
    def load_regions(self) -> dict[str, Region]:
        ...

    @abstractmethod
    def load_scenarios(self) -> list[Scenario]:
        ...

    @abstractmethod
    def source_file_hashes(self) -> dict[str, str]:
        """manifest 기록용: {파일경로: sha256}."""


class DummyFileInputSource(InputSource):
    """data/input/ 아래의 가상 파일로부터 로드한다 (1차 개발 범위)."""

    def __init__(self, base_dir: str | Path,
                 assumptions_file: str = "assumptions.json",
                 reward_levels_file: str = "reward_levels.csv",
                 regions_file: str = "regions.csv",
                 scenarios_file: str = "scenarios.csv"):
        self.base_dir = Path(base_dir)
        self.assumptions_path = self.base_dir / assumptions_file
        self.reward_levels_path = self.base_dir / reward_levels_file
        self.regions_path = self.base_dir / regions_file
        self.scenarios_path = self.base_dir / scenarios_file

    def load_assumptions(self) -> tuple[dict[str, Assumption], str]:
        with open(self.assumptions_path, encoding="utf-8") as f:
            data = json.load(f)
        out = {}
        for row in data["assumptions"]:
            a = Assumption(
                key=row["key"], value=float(row["value"]), unit=row.get("unit", ""),
                value_type=row["value_type"], source=row["source"], period=row["period"],
                notes=row.get("notes", ""),
            )
            out[a.key] = a
        return out, data["as_of_date"]

    def load_reward_levels(self) -> dict[str, RewardLevel]:
        out = {}
        with open(self.reward_levels_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rl = RewardLevel(
                    reward_level_id=row["reward_level_id"], label=row["label"],
                    reward_cost_per_conversion=float(row["reward_cost_per_conversion"]),
                    value_type=row["value_type"], source=row["source"], period=row["period"],
                )
                out[rl.reward_level_id] = rl
        return out

    def load_regions(self) -> dict[str, Region]:
        out = {}
        with open(self.regions_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                r = Region(
                    region_id=row["region_id"], region_name=row["region_name"],
                    tourist_share=float(row["tourist_share"]),
                    contacted_customers_per_fm=float(row["contacted_customers_per_fm"]),
                    fixed_operation_cost_per_fm=float(row["fixed_operation_cost_per_fm"]),
                    value_type=row["value_type"], source=row["source"], period=row["period"],
                )
                out[r.region_id] = r
        return out

    def load_scenarios(self) -> list[Scenario]:
        out = []
        with open(self.scenarios_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                out.append(Scenario(
                    scenario_id=row["scenario_id"], region_id=row["region_id"],
                    fm_count=int(row["fm_count"]), reward_level_id=row["reward_level_id"],
                    label=row["label"],
                ))
        return out

    def source_file_hashes(self) -> dict[str, str]:
        paths = [self.assumptions_path, self.reward_levels_path, self.regions_path, self.scenarios_path]
        return {str(p.relative_to(self.base_dir.parent.parent)): sha256_of_file(p) for p in paths if p.exists()}


class UnconnectedInputSource(InputSource):
    """공개/사내 데이터 연결용 자리표시자.

    실제 API/DB 연결이 준비되기 전까지는 절대 '연결된 것처럼' 동작하지 않는다.
    호출 시 명확한 에러로 실패시켜, 연결되지 않은 상태를 숨기지 않는다.
    """

    def __init__(self, name: str):
        self.name = name

    def _fail(self):
        raise NotImplementedError(
            f"'{self.name}' 데이터 소스는 아직 연결되지 않았습니다. "
            f"1차 개발 범위(가상 파일 기반)에는 포함되지 않습니다."
        )

    def load_assumptions(self):
        self._fail()

    def load_reward_levels(self):
        self._fail()

    def load_regions(self):
        self._fail()

    def load_scenarios(self):
        self._fail()

    def source_file_hashes(self):
        self._fail()
