"""Descriptive grouping of raw detector events into episodes (v1).

Vocabulary (never signals, never opportunities):
- raw event: one original emission, preserved verbatim (never mutated,
  never dropped silently: malformed rows are counted as skipped).
- grouped episode: maximal sequence under the v1 rule below.
- update: a repetition or evolution inside the episode (same key,
  contiguous in time).
- new episode: the separation rule fires (key change or time gap).

Grouping is descriptive interpretation of repetition, not an entry
signal and not a claim of independent samples. Detector conditions and
thresholds live in detectors.py/config and are untouched here.

v1 rule (extreme_funding_rate):
- grouping key: (event_type, symbol, funding_rate).
- order: by (symbol, timestamp); the input order is never assumed.
- same episode while key is equal AND gap <= MAX_GAP_S (5s) between
  consecutive observations.
- new episode on: first usable record ("first-event"), symbol change,
  rate change ("new-rate"), or gap exceeded ("gap-exceeded").
- close reason: "superseded" when a new episode opens, "end-of-evidence"
  for the trailing episode of each run of records.
- each episode records: grouping_version, episode_id, event_type,
  symbol, funding_rate, repetitions (raw count, duplicates included),
  duplicate_records, first/last observation ISO, duration_s,
  history_samples first->last, open/close reason, and the input indexes
  it groups (audit trail back to the preserved originals).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

GROUPING_VERSION = "v1"
MAX_GAP_S = 5.0


def _parse_ts(value: Any) -> Optional[float]:
    try:
        if not isinstance(value, str) or not value.strip():
            return None
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return None


def _finite_number(value: Any) -> Optional[float]:
    try:
        if isinstance(value, bool):
            return None
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if num == num else None


def group_funding_episodes(events: Any) -> Dict[str, Any]:
    """Group raw extreme_funding_rate events into v1 episodes.

    Input: list of dicts with timestamp (ISO str), symbol (str),
    funding_rate (number), history_samples (int, optional).
    Never mutates the input. Returns {grouping_version, rule,
    episodes[], skipped, total}.
    """
    episodes: List[Dict[str, Any]] = []
    skipped = 0
    usable: List[Dict[str, Any]] = []
    if isinstance(events, list):
        for index, item in enumerate(events):
            if not isinstance(item, dict):
                skipped += 1
                continue
            ts = _parse_ts(item.get("timestamp"))
            symbol = item.get("symbol")
            rate = _finite_number(item.get("funding_rate"))
            if ts is None or not isinstance(symbol, str) or not symbol \
                    or rate is None:
                skipped += 1
                continue
            usable.append({"index": index, "ts": ts,
                           "timestamp": item["timestamp"],
                           "symbol": symbol, "rate": rate,
                           "samples": item.get("history_samples")})
    usable.sort(key=lambda r: (r["symbol"], r["ts"], r["index"]))
    current: Optional[Dict[str, Any]] = None

    def _close(episode: Dict[str, Any], reason: str) -> None:
        episode["close_reason"] = reason
        episode["duration_s"] = round(
            max(0.0, episode["last_ts"] - episode["first_ts"]), 3)
        episodes.append(episode)

    def _open(record: Dict[str, Any], reason: str) -> Dict[str, Any]:
        return {
            "grouping_version": GROUPING_VERSION,
            "episode_id": "%s/%s/%s" % (record["symbol"], repr(record["rate"]),
                                        record["timestamp"]),
            "event_type": "extreme_funding_rate",
            "symbol": record["symbol"],
            "funding_rate": record["rate"],
            "repetitions": 0,
            "duplicate_records": 0,
            "first_observed_at": record["timestamp"],
            "last_observed_at": record["timestamp"],
            "first_ts": record["ts"],
            "last_ts": record["ts"],
            "samples_first": record["samples"],
            "samples_last": record["samples"],
            "open_reason": reason,
            "close_reason": None,
            "event_indexes": [],
            "_seen": set(),
        }

    for record in usable:
        key = (record["symbol"], record["rate"])
        cur_key = (current["symbol"], current["funding_rate"]) \
            if current is not None else None
        dupe = (record["timestamp"], record["symbol"], record["rate"],
                record["samples"]) in (current["_seen"] if current else set())
        if current is not None and cur_key == key \
                and (record["ts"] - current["last_ts"]) <= MAX_GAP_S:
            current["repetitions"] += 1
            if dupe:
                current["duplicate_records"] += 1
            current["_seen"].add((record["timestamp"], record["symbol"],
                                  record["rate"], record["samples"]))
            current["last_observed_at"] = record["timestamp"]
            current["last_ts"] = record["ts"]
            current["samples_last"] = record["samples"]
            current["event_indexes"].append(record["index"])
            continue
        if current is not None:
            if cur_key != key:
                _close(current, "superseded")
            else:
                _close(current, "gap-exceeded")
        if not episodes and current is None:
            reason = "first-event"
        elif current is not None and current["symbol"] != record["symbol"]:
            reason = "new-symbol"
        elif current is not None and current["funding_rate"] != record["rate"]:
            reason = "new-rate"
        elif current is not None:
            reason = "gap-exceeded"
        else:
            reason = "first-event"
        current = _open(record, reason)
        current["repetitions"] = 1
        current["_seen"].add((record["timestamp"], record["symbol"],
                              record["rate"], record["samples"]))
        current["event_indexes"].append(record["index"])
    if current is not None:
        _close(current, "end-of-evidence")
    for episode in episodes:
        episode.pop("_seen", None)
        episode.pop("first_ts", None)
        episode.pop("last_ts", None)
    return {
        "grouping_version": GROUPING_VERSION,
        "rule": {"key": ["event_type", "symbol", "funding_rate"],
                 "max_gap_s": MAX_GAP_S,
                 "order": ["symbol", "timestamp"],
                 "note": "descriptive grouping only; episodes are not "
                         "independent samples and never entry signals"},
        "episodes": episodes,
        "skipped": skipped,
        "total": len(events) if isinstance(events, list) else 0,
    }
