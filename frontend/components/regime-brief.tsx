"use client";

import { useState } from "react";
import { postRegimeBrief, type AiBrief } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Badge, Panel, Skeleton } from "@/components/ui";

export function RegimeBrief() {
  const { t } = useI18n();
  const [brief, setBrief] = useState<AiBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const generate = async () => {
    setLoading(true);
    setErr(null);
    try {
      setBrief(await postRegimeBrief());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Panel
      title={t("home.aiBrief")}
      right={
        brief ? (
          <Badge tone={brief.source === "llm" ? "accent" : "flat"}>
            {brief.source === "llm" ? `LLM · ${brief.model ?? ""}` : t("home.aiRule")}
          </Badge>
        ) : undefined
      }
    >
      {!brief && !loading && !err && (
        <div className="flex flex-col items-start gap-2">
          <p className="text-xs text-term-muted">
            {t("asset.aiChatEmpty") === "Ask the AI about this asset's indicators and trend."
              ? "Generate a technical analysis briefing from today's market regime data."
              : t("home.aiRuleDesc")}
          </p>
          <button type="button" onClick={() => void generate()} className="btn-primary px-4 py-1.5 text-xs">
            {t("home.aiBrief")} ▸
          </button>
        </div>
      )}
      {loading && <Skeleton rows={3} />}
      {err && (
        <div className="space-y-2">
          <p className="text-xs text-down">{err}</p>
          <button type="button" onClick={() => void generate()} className="btn-primary px-3 py-1 text-xs">
            {t("common.retry")}
          </button>
        </div>
      )}
      {brief && !loading && (
        <div className="space-y-2.5">
          <ul className="space-y-1.5">
            {brief.summary.map((s, i) => (
              <li key={i} className="flex gap-2 text-xs leading-relaxed text-zinc-300">
                <span className="mt-0.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                {s}
              </li>
            ))}
          </ul>
          <div>
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="text-[11px] text-accent hover:underline"
            >
              {open ? t("home.aiBriefHide") : t("home.aiBriefDetail")}
            </button>
            {open && (
              <div className="mt-2 space-y-2 border-s-2 border-accent/30 ps-3">
                <p className="whitespace-pre-wrap text-xs leading-relaxed text-zinc-300">
                  {brief.detail}
                </p>
                {brief.uncertainty && (
                  <p className="text-[11px] leading-relaxed text-term-muted">
                    ⚠ {brief.uncertainty}
                  </p>
                )}
              </div>
            )}
          </div>
          {brief.error && <p className="text-[10px] text-down">{brief.error}</p>}
          <p className="border-t border-term-border pt-2 text-[10px] text-term-dim">
            ⚠️ {t("common.disclaimer")}
          </p>
        </div>
      )}
    </Panel>
  );
}
