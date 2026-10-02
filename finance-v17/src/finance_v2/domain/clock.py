from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def now_utc(self) -> datetime: ...
    def today(self) -> date: ...


def utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class SystemClock:
    timezone_name: str

    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc).replace(microsecond=0)

    def today(self) -> date:
        return self.now_utc().astimezone(ZoneInfo(self.timezone_name)).date()


@dataclass(frozen=True)
class FixedClock:
    instant: datetime
    timezone_name: str = "America/Sao_Paulo"

    def now_utc(self) -> datetime:
        if self.instant.tzinfo is None:
            raise ValueError("controlled clock instant must be timezone-aware")
        return self.instant.astimezone(timezone.utc).replace(microsecond=0)

    def today(self) -> date:
        return self.now_utc().astimezone(ZoneInfo(self.timezone_name)).date()
