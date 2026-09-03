"use client";

import { use } from "react";
import { AssetDetailView } from "@/components/asset-detail";

export default function AssetPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol: raw } = use(params);
  const symbol = decodeURIComponent(raw).toUpperCase();
  return <AssetDetailView symbol={symbol} />;
}
