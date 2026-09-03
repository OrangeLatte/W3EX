"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getAgents, postAgentChat, type AgentMeta, type AgentReply, type AgentToolStep } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { ErrorPanel, Panel } from "@/components/ui";

interface Msg {
  role: "user" | "assistant";
  content: string;
  source?: string;
  tools?: AgentToolStep[];
}

const AGENT_KEY_I18N: Record<string, string> = {
  mentor: "agent.mentor",
  scout: "agent.scout",
  risk: "agent.risk",
  review: "agent.review",
};

function AgentPage() {
  const { t, lang } = useI18n();
  const [agents, setAgents] = useState<AgentMeta[]>([]);
  const [kind, setKind] = useState<string>("scout");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    getAgents()
      .then((list) => alive && setAgents(list))
      .catch((e) => alive && setLoadErr(e?.message ?? t("common.error")));
    return () => {
      alive = false;
    };
  }, []);

  // 切换教练 → 加载该教练的本地会话
  useEffect(() => {
    if (!kind) return;
    try {
      const raw = localStorage.getItem(`w3ex_agent_${kind}`);
      setMessages(raw ? (JSON.parse(raw) as Msg[]) : []);
    } catch {
      setMessages([]);
    }
    setInput("");
    setError(null);
  }, [kind]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const persist = useCallback(
    (kindKey: string, msgs: Msg[]) => {
      try {
        localStorage.setItem(`w3ex_agent_${kindKey}`, JSON.stringify(msgs.slice(-40)));
      } catch {
        // 存储满等异常忽略
      }
    },
    []
  );

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setError(null);
    const userMsg: Msg = { role: "user", content: text };
    const next = [...messages, userMsg];
    setMessages(next);
    setSending(true);
    try {
      const history = messages
        .filter((m) => m.content)
        .slice(-20)
        .map((m) => ({ role: m.role, content: m.content }));
      const reply: AgentReply = await postAgentChat(kind, { message: text, history, lang });
      const done: Msg[] = [
        ...next,
        { role: "assistant", content: reply.reply, source: reply.source, tools: reply.tool_trace },
      ];
      setMessages(done);
      persist(kind, done);
    } catch (e) {
      // 部分输出保留：保留用户消息并提示重试
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }, [input, sending, messages, kind, persist]);

  const current = agents.find((a) => a.kind === kind);

  return (
    <div className="space-y-4">
      <Panel title={t("agent.title")}>
        {loadErr ? (
          <ErrorPanel message={loadErr} onRetry={() => getAgents().then(setAgents).catch(() => {})} />
        ) : agents.length === 0 ? (
          <div className="h-8 w-2/3 animate-pulse rounded bg-term-panel2" />
        ) : (
          <div className="flex flex-wrap gap-2">
            {agents.map((a) => (
              <button
                key={a.kind}
                type="button"
                onClick={() => setKind(a.kind)}
                className={`rounded border px-3 py-1.5 text-xs transition-colors ${
                  kind === a.kind
                    ? "border-ai bg-ai/10 text-ai"
                    : "border-term-border text-term-muted hover:border-term-accent hover:text-term-accent"
                }`}
              >
                <span className="num">{t(AGENT_KEY_I18N[a.kind] ?? a.kind)}</span>
                <span className="ms-2 opacity-60">{a.style}</span>
              </button>
            ))}
          </div>
        )}
        {current && <p className="mt-2 text-xs text-term-dim">{current.name_en}</p>}
      </Panel>

      <Panel title={t(AGENT_KEY_I18N[kind] ?? kind)}>
        <div className="flex h-[480px] flex-col">
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pe-1">
            {messages.length === 0 && (
              <p className="pt-8 text-center text-xs text-term-dim">{t("agent.empty")}</p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                <div
                  className={`max-w-[85%] whitespace-pre-wrap rounded border px-3 py-2 text-sm leading-relaxed ${
                    m.role === "user"
                      ? "border-ai/40 bg-ai/5 text-term-fg"
                      : "border-term-border bg-term-panel2 text-term-fg"
                  }`}
                >
                  {m.content}
                  {m.tools && m.tools.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {m.tools.map((s, i) => (
                        <span
                          key={`${s.tool}-${i}`}
                          title={s.summary}
                          className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] num ${
                            s.ok
                              ? "border-term-border text-term-accent"
                              : "border-term-down/40 text-term-down"
                          }`}
                        >
                          🔧 {s.tool}
                          {Object.keys(s.args ?? {}).length > 0 &&
                            `(${Object.entries(s.args)
                              .map(([k, v]) => `${k}=${String(v)}`)
                              .join(",")})`}
                          {s.ok ? " ✓" : " ✗"}
                        </span>
                      ))}
                    </div>
                  )}
                  {m.source && (
                    <span className="ms-2 align-middle text-[10px] text-term-dim">
                      {m.source.startsWith("llm") ? `LLM·${m.source.split(":")[1] ?? ""}` : t("common.ruleEngine")}
                    </span>
                  )}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="rounded border border-term-border bg-term-panel2 px-3 py-2 text-sm text-term-dim">
                  <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-term-accent" />{" "}
                  {t("common.loading")}
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {error && (
            <p className="mt-2 text-xs text-term-down">
              {error}{" "}
              <button type="button" className="text-term-accent underline" onClick={send}>
                {t("common.retry")}
              </button>
            </p>
          )}

          <div className="mt-3 flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.nativeEvent.isComposing) void send();
              }}
              placeholder={t("agent.placeholder")}
              className="num flex-1 rounded border border-term-border bg-term-panel2 px-3 py-2 text-sm outline-none focus:border-term-accent"
            />
            <button
              type="button"
              onClick={() => void send()}
              disabled={sending || !input.trim()}
              className="btn-primary rounded px-4 py-2 text-sm disabled:opacity-40"
            >
              {t("common.send")}
            </button>
            <button
              type="button"
              onClick={() => {
                setMessages([]);
                persist(kind, []);
              }}
              className="rounded border border-term-border px-3 py-2 text-xs text-term-muted hover:text-term-down"
            >
              {t("asset.chatClear")}
            </button>
          </div>
          <p className="mt-2 text-[10px] text-term-dim">{t("common.disclaimer")}</p>
        </div>
      </Panel>
    </div>
  );
}

export default function Page() {
  return (
    <div className="mx-auto max-w-4xl">
      <AgentPage />
    </div>
  );
}
