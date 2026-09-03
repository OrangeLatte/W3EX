"use client";

import { useI18n } from "@/lib/i18n";
import { getLastDataMeta } from "@/lib/api";

/** 评审 P0 数据可信度：mock 兑底时显眼警示，真实源时低调标注来源。 */
export function DataBadge() {
  const { t } = useI18n();
  const { source, quality } = getLastDataMeta();
  if (quality === "simulated") {
    return (
      <span
        title={t("data.simulatedTip")}
        className="inline-flex items-center gap-1 rounded border border-amber-500/60 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-400"
      >
        ⚠ {t("data.simulated")}
      </span>
    );
  }
  if (!source) return null;
  return (
    <span className="rounded border border-term-border px-1.5 py-0.5 text-[10px] text-term-dim">
      {t("data.source")}: {source}
    </span>
  );
}
