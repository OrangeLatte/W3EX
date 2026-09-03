"use client";

import { useEffect, useRef, useState } from "react";
import { postAssetChatStream, type ChatStreamEvent } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  autoTitle,
  deleteSession,
  loadSessions,
  newSession,
  saveSessions,
  type ChatSession,
  type Msg,
} from "@/lib/chat-store";

const FALLBACK_INTERVAL = "1h";
const CHAT_INTERVALS: Record<string, string> = { "1m": "5m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d" };
const STAGE_KEYS: Record<string, string> = { context: "asset.stepContext", generating: "asset.stepGenerating" };
const HEIGHT_KEY = "w3ex_chat_height";

export function AiChatPanel({ symbol, interval }: { symbol: string; interval: string }) {
  const { t } = useI18n();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [step, setStep] = useState<string | null>(null);
  const [chatInterval, setChatInterval] = useState(interval);
  const [height, setHeight] = useState(440);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 挂载：恢复会话列表（无则建新），恢复高度偏好
  useEffect(() => {
    const saved = Number(localStorage.getItem(HEIGHT_KEY));
    if (saved >= 320 && saved <= 720) setHeight(saved);
    let list = loadSessions(symbol);
    if (list.length === 0) {
      const s = newSession();
      list = [s];
      saveSessions(symbol, list);
    }
    setSessions(list);
    setActiveId(list[0].id);
    setMessages(list[0].messages);
  }, [symbol]);

  useEffect(() => {
    setChatInterval(CHAT_INTERVALS[interval] ?? FALLBACK_INTERVAL);
  }, [interval]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, sending, step]);

  // 持久化：非发送中把当前 messages 写回活跃会话
  useEffect(() => {
    if (sending || !activeId) return;
    setSessions((prev) => {
      const next = prev.map((s) =>
        s.id === activeId
          ? { ...s, messages, updated_at: new Date().toISOString(), title: s.title || autoTitle(messages) }
          : s,
      );
      saveSessions(symbol, next);
      return next;
    });
  }, [messages, sending, activeId, symbol]);

  const switchSession = (id: string) => {
    if (sending) return;
    const s = sessions.find((x) => x.id === id);
    if (!s) return;
    setActiveId(id);
    setMessages(s.messages);
  };

  const createSession = () => {
    if (sending) return;
    const s = newSession();
    const next = [s, ...sessions];
    setSessions(next);
    saveSessions(symbol, next);
    setActiveId(s.id);
    setMessages([]);
  };

  const removeSession = (id: string) => {
    if (sending || !window.confirm(t("asset.chatDeleteConfirm"))) return;
    const next = deleteSession(symbol, id);
    if (next.length === 0) {
      const s = newSession();
      const withNew = [s];
      setSessions(withNew);
      saveSessions(symbol, withNew);
      setActiveId(s.id);
      setMessages([]);
      return;
    }
    setSessions(next);
    if (activeId === id) {
      setActiveId(next[0].id);
      setMessages(next[0].messages);
    }
  };

  const changeHeight = (v: number) => {
    setHeight(v);
    try {
      localStorage.setItem(HEIGHT_KEY, String(v));
    } catch {
      /* ignore */
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    const history = messages.filter((m) => !m.streaming).slice(-20).map((m) => ({ role: m.role, content: m.content }));
    setMessages((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "", streaming: true }]);
    setSending(true);
    setStep("context");
    const onEvent = (ev: ChatStreamEvent) => {
      if (ev.type === "step") {
        setStep(ev.stage ?? null);
      } else if (ev.type === "delta" && ev.text) {
        setMessages((m) => {
          const copy = [...m];
          const last = copy[copy.length - 1];
          if (last?.role === "assistant") copy[copy.length - 1] = { ...last, content: last.content + ev.text };
          return copy;
        });
      } else if (ev.type === "error") {
        setMessages((m) => {
          const copy = [...m];
          const last = copy[copy.length - 1];
          if (last?.role === "assistant") copy[copy.length - 1] = { ...last, error: ev.message ?? null };
          return copy;
        });
      } else if (ev.type === "done") {
        setMessages((m) => {
          const copy = [...m];
          const last = copy[copy.length - 1];
          if (last?.role === "assistant")
            copy[copy.length - 1] = { ...last, streaming: false, source: ev.source ?? "rule" };
          return copy;
        });
      }
    };
    try {
      await postAssetChatStream(symbol, { message: text, interval: chatInterval, history }, onEvent);
    } catch (e) {
      setMessages((m) => {
        const copy = [...m];
        const last = copy[copy.length - 1];
        if (last?.role === "assistant" && !last.content)
          copy[copy.length - 1] = {
            ...last,
            content: t("common.error"),
            streaming: false,
            source: "rule",
            error: e instanceof Error ? e.message : String(e),
          };
        else if (last?.role === "assistant")
          copy[copy.length - 1] = { ...last, streaming: false, error: e instanceof Error ? e.message : String(e) };
        return copy;
      });
    } finally {
      setSending(false);
      setStep(null);
    }
  };

  const activeSession = sessions.find((s) => s.id === activeId);

  return (
    <div className="flex flex-col" style={{ height }}>
      {/* 会话管理条：切换 / 新建 / 删除 + 高度滑块 */}
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
        <select
          value={activeId ?? ""}
          onChange={(e) => switchSession(e.target.value)}
          className="max-w-[160px] rounded border border-term-border bg-term-bg px-1.5 py-1 text-[11px] text-zinc-300 outline-none"
          title={activeSession?.title || ""}
        >
          {sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title || t("asset.chatNew")}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={createSession}
          disabled={sending}
          className="rounded border border-accent/40 bg-accent/10 px-2 py-1 text-[10px] text-accent hover:bg-accent/20 disabled:opacity-40"
        >
          + {t("asset.chatNew")}
        </button>
        {activeId && (
          <button
            type="button"
            onClick={() => removeSession(activeId)}
            disabled={sending || sessions.length <= 1}
            className="rounded border border-term-border px-2 py-1 text-[10px] text-term-dim hover:border-down/50 hover:text-down disabled:opacity-40"
          >
            {t("asset.chatDelete")}
          </button>
        )}
        <label className="ms-auto flex items-center gap-1.5 text-[10px] text-term-dim">
          <span>↕</span>
          <input
            type="range"
            min={320}
            max={720}
            step={20}
            value={height}
            onChange={(e) => changeHeight(Number(e.target.value))}
            className="w-24 accent-[var(--color-accent)]"
          />
        </label>
      </div>
      {sending && step && (
        <span className="mb-1 inline-flex w-fit items-center gap-1 rounded bg-accent/10 px-2 py-0.5 text-[10px] text-accent">
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
          {t(STAGE_KEYS[step] ?? "common.loading")}
        </span>
      )}
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto pe-1">
        {messages.length === 0 && (
          <p className="py-8 text-center text-xs text-term-dim">{t("asset.aiChatEmpty")}</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={`max-w-[88%] whitespace-pre-wrap rounded-lg px-3 py-2 text-xs leading-relaxed ${
                m.role === "user"
                  ? "bg-accent/15 text-zinc-100"
                  : "border border-term-border bg-term-panel2 text-zinc-300"
              }`}
            >
              {m.content}
              {m.streaming && <span className="ms-1 inline-block animate-pulse text-accent">▍</span>}
              {m.role === "assistant" && !m.streaming && (
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] text-term-dim">
                  {m.source === "llm" && <span className="text-accent">LLM</span>}
                  {m.source === "rule" && !m.error && <span>{t("home.aiRule")}</span>}
                  {m.error && <span className="text-down">{m.error}</span>}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-2 border-t border-term-border pt-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.nativeEvent.isComposing) void send();
          }}
          placeholder={t("asset.aiChatPlaceholder")}
          className="flex-1 rounded border border-term-border bg-term-bg px-3 py-1.5 text-xs text-zinc-200 outline-none focus:border-accent/50"
        />
        <button type="button" onClick={() => void send()} disabled={sending || !input.trim()} className="btn-primary px-3 py-1.5 text-xs">
          {t("asset.aiChatSend")}
        </button>
      </div>
      <p className="mt-1.5 text-[10px] leading-relaxed text-term-dim">
        {!messages.some((m) => m.source === "llm") && <span>💡 {t("asset.notBound")} </span>}
        ⚠️ {t("common.disclaimer")}
      </p>
    </div>
  );
}
