"""Domain models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Hit:
    kind: str
    number: str
    page: int
    ids: list[str] = field(default_factory=list)
    slug: str | None = None
    title: str = ""
    asset: str | None = None
    url: str | None = None
    relevant: bool = False
    denomination: str = ""
    alloy: str = ""
    mintage: str = ""
    effective: str = ""

    @property
    def key(self) -> str:
        return f"{self.kind.split()[0]}:{self.number}"
