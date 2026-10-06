# SAFETY_RULES

Current state: **OBSERVE ONLY.** These rules keep it so.

## Forbidden without explicit human authorization

- Private Binance account APIs (any signed/authenticated endpoint).
- API keys anywhere in repo, env files, logs, or chat.
- Order placement, cancellation, amendment.
- Leverage changes, position changes, margin moves.
- Signing anything, broadcasting anything.
- Withdrawals / transfers / any fund movement.
- Live capital, any size, any "just to test".
- Enabling any execution engine or path.

## Active enforcement

- `BOT_MODE=observe` default; any other value aborts startup. No other mode
  is supported by this codebase.
- No authenticated client code, no order functions exist. Static test
  `test_source_contains_no_order_or_authenticated_client_paths` fails the suite
  if such paths appear.
- Summaries always print the safety block
  (`BOT_MODE`, `apiKeysUsed: 0`, `realOrdersSent: 0`, `realCapitalAtRisk: 0`).
- `.gitignore` excludes `.env`, `secrets/`, `private/`, keys, logs, data, DBs.

## Handling

- Never paste secrets into chat, logs, or docs. If a secret is accidentally
  exposed: stop, rotate/revoke it, remove it from history, record a
  `docs/DECISIONS.md` entry.
- Never fetch remote code into the probe path without audit.
- Soak/live verification uses public streams only; capturing logs externally
  via `Tee-Object` keeps ad-hoc persistence out of the probe. Durable storage
  goes only through the P1-02 persistence foundation (local, observe-only).
- Dashboard startup/restart must never start trading or require Binance
  private credentials. Dashboard commands operate only on the Binance
  dashboard (dedicated port, 127.0.0.1); never kill unrelated processes on
  port conflict — pick another free port and document it.

## Escalation

Any task that would need keys, signing, private endpoints, or capital STOPS
the autonomous loop immediately and asks the human. No exceptions, no
"temporary" bypasses.
