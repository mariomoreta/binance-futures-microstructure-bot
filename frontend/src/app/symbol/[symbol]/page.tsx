import { notFound } from "next/navigation";
import { TokenDetail } from "@/components/token/TokenDetail";
import { getDemoTokenDetail } from "@/lib/token-detail";

export default async function SymbolPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  if (!/^[A-Za-z0-9_-]{2,32}$/.test(symbol)) notFound();
  return <TokenDetail data={getDemoTokenDetail(symbol)} />;
}
