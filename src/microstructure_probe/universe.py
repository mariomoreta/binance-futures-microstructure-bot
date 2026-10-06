"""P1-04 symbol universe: explicit, extensible, no silent expansion.

The active validated universe stays BTCUSDT/ETHUSDT/SOLUSDT. Growing it
(future exchangeInfo-driven expansion) must not require rewriting the
feature engine: engines key off SymbolUniverse.active_symbols().
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional


@dataclass(frozen=True)
class SymbolInfo:
    """One universe entry with explicit inclusion metadata."""
    symbol: str
    enabled: bool = True
    source: str = "static-config"
    reason: str = ""
    activated_at: Optional[str] = None  # ISO-8601 UTC, where useful


class SymbolUniverse:
    """Explicit set of symbols the pipeline may observe and model."""

    def __init__(self, infos: Iterable[SymbolInfo]) -> None:
        infos = tuple(infos)
        seen = set()
        for info in infos:
            upper = info.symbol.upper()
            if upper in seen:
                raise ValueError(f"duplicate universe symbol: {info.symbol}")
            seen.add(upper)
        self._infos = infos
        self._by_symbol = {info.symbol.upper(): info for info in infos}

    @classmethod
    def from_config(cls, config, *,
                    reason: str = "",
                    activated_at: Optional[str] = None) -> "SymbolUniverse":
        """Build from ProbeConfig.symbols (static-config source)."""
        if activated_at is None:
            activated_at = datetime.now(timezone.utc).isoformat()
        return cls(
            SymbolInfo(symbol=symbol, enabled=True, source="static-config",
                       reason=reason, activated_at=activated_at)
            for symbol in config.symbols
        )

    @classmethod
    def from_list(cls, symbols: Iterable[str], *, source: str,
                  reason: str) -> "SymbolUniverse":
        """Build from an explicit list (future exchangeInfo expansion path)."""
        return cls(
            SymbolInfo(symbol=symbol, enabled=True, source=source, reason=reason)
            for symbol in symbols
        )

    def active_symbols(self) -> tuple[str, ...]:
        return tuple(info.symbol for info in self._infos if info.enabled)

    def get(self, symbol: str) -> Optional[SymbolInfo]:
        return self._by_symbol.get(symbol.upper())

    def __contains__(self, symbol: object) -> bool:
        return isinstance(symbol, str) and symbol.upper() in self._by_symbol

    def __len__(self) -> int:
        return len(self._infos)

    def __iter__(self) -> Iterator[SymbolInfo]:
        return iter(self._infos)
