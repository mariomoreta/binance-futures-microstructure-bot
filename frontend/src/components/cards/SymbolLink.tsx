import Link from "next/link";

export function SymbolLink({ symbol }: { symbol: string }) {
  return (
    <Link
      href={`/symbol/${encodeURIComponent(symbol)}`}
      className="v2-mono"
      data-testid="symbol-link"
    >
      {symbol}
    </Link>
  );
}
