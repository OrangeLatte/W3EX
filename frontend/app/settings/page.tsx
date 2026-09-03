"use client";

import { useCallback, useEffect, useState } from "react";
import {
  bindAi,
  getAiModels,
  getAiStatus,
  unbindAi,
  type AiBindResult,
  type AiStatus,
} from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { Badge, ErrorPanel, Panel, Skeleton } from "@/components/ui";

export default function SettingsPage() {
  const { t } = useI18n();
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [provider, setProvider] = useState("openai_compatible");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [label, setLabel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [bound, setBound] = useState<AiBindResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    getAiStatus()
      .then((s) => {
        setStatus(s);
        setLoadErr(null);
        if (s.bound && s.provider) setProvider(s.provider);
      })
      .catch((e) => setLoadErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const doBind = async (chosenModel: string | null) => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await bindAi({
        provider,
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
        model: chosenModel,
        label: label.trim(),
      });
      setBound(res);
      setModels(res.models);
      setModel(res.model ?? "");
      setMsg({
        kind: "ok",
        text: chosenModel ? `${t("settings.bound")} · ${res.model}` : t("settings.autoDetected"),
      });
      load();
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  const refreshModels = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await getAiModels();
      setModels(res.models);
      setMsg({ kind: "ok", text: `${t("settings.modelsFound")}: ${res.models.length}` });
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  const doUnbind = async () => {
    setBusy(true);
    try {
      await unbindAi();
      setStatus({ bound: false });
      setBound(null);
      setModels([]);
      setMsg({ kind: "ok", text: t("settings.unbind") + " ✓" });
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  const input =
    "w-full rounded border border-term-border bg-term-bg px-3 py-1.5 text-xs text-zinc-200 outline-none focus:border-accent/50";
  const btn =
    "rounded px-4 py-1.5 text-xs font-medium disabled:opacity-40 border border-term-border bg-term-panel2 text-zinc-200 hover:bg-term-border/40";

  if (loading && !status) return <Skeleton rows={6} />;

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <h1 className="text-lg font-bold text-zinc-100">{t("settings.title")}</h1>
        <p className="mt-1 text-xs text-term-muted">{t("settings.subtitle")}</p>
      </div>

      <Panel
        title={t("settings.status")}
        right={
          status?.bound ? (
            <Badge tone="up">{t("settings.bound")}</Badge>
          ) : (
            <Badge tone="flat">{t("settings.notBound")}</Badge>
          )
        }
      >
        {loadErr && <ErrorPanel message={loadErr} />}
        {status?.bound ? (
          <div className="space-y-1.5 text-xs">
            <p>
              <span className="text-term-dim">Provider: </span>
              <span className="num text-zinc-200">{status.provider}</span>
              {status.label && <span className="ms-2 text-term-dim">({status.label})</span>}
            </p>
            <p>
              <span className="text-term-dim">Model: </span>
              <span className="num text-zinc-200">{status.model ?? "—"}</span>
            </p>
            <p>
              <span className="text-term-dim">Base URL: </span>
              <span className="num text-zinc-400">{status.base_url}</span>
            </p>
            <p>
              <span className="text-term-dim">API Key: </span>
              <span className="num text-zinc-400">{status.api_key_masked}</span>
            </p>
            {status.last_checked_at && (
              <p className="text-term-dim">
                {t("settings.lastChecked")}: {timeAgo(status.last_checked_at)}
              </p>
            )}
            <button type="button" onClick={() => void doUnbind()} disabled={busy} className={`${btn} mt-2 text-down`}>
              {t("settings.unbind")}
            </button>
          </div>
        ) : (
          <p className="text-xs text-term-muted">{t("settings.subtitle")}</p>
        )}
      </Panel>

      <Panel title={t("settings.bind")}>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-[10px] uppercase tracking-wider text-term-dim">
              {t("settings.provider")}
            </label>
            <div className="flex gap-2">
              {(
                [
                  ["openai_compatible", t("settings.providerOpenai")],
                  ["anthropic", t("settings.providerAnthropic")],
                ] as const
              ).map(([val, lbl]) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setProvider(val)}
                  className={`rounded border px-3 py-1.5 text-xs ${
                    provider === val
                      ? "border-accent/50 bg-accent/10 text-accent"
                      : "border-term-border text-term-muted hover:text-zinc-200"
                  }`}
                >
                  {lbl}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-[10px] uppercase tracking-wider text-term-dim">
              {t("settings.baseUrl")}
            </label>
            <input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
              className={input}
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] uppercase tracking-wider text-term-dim">
              {t("settings.apiKey")}
            </label>
            <input
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              type="password"
              placeholder="sk-…"
              className={input}
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] uppercase tracking-wider text-term-dim">
              {t("settings.label")}
            </label>
            <input value={label} onChange={(e) => setLabel(e.target.value)} className={input} />
          </div>

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={() => void doBind(null)}
              disabled={busy || !baseUrl.trim() || !apiKey.trim()}
              className="btn-primary px-4 py-1.5 text-xs"
            >
              {busy ? t("common.loading") : t("settings.bind")}
            </button>
            {status?.bound && (
              <button type="button" onClick={() => void refreshModels()} disabled={busy} className={btn}>
                {t("settings.modelsFound")}
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                setProvider("openai_compatible");
                setBaseUrl("https://open.bigmodel.cn/api/paas/v4");
                setLabel("Zhipu GLM");
              }}
              disabled={busy}
              className={btn}
              title={t("settings.zhipuPreset")}
            >
              {t("settings.zhipuPreset")}
            </button>
          </div>

          {msg && (
            <p className={`text-xs ${msg.kind === "ok" ? "text-up" : "text-down"}`}>{msg.text}</p>
          )}

          {models.length > 0 && (
            <div className="border-t border-term-border pt-3">
              <label className="mb-1 block text-[10px] uppercase tracking-wider text-term-dim">
                {t("settings.model")} · {models.length}
              </label>
              <div className="flex gap-2">
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className={`${input} flex-1`}
                >
                  {models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => void doBind(model || null)}
                  disabled={busy || !model}
                  className={btn}
                >
                  {t("settings.saveModel")}
                </button>
              </div>
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}
