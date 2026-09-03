"use client";

export interface Msg {
  role: "user" | "assistant";
  content: string;
  source?: "rule" | "llm";
  error?: string | null;
  streaming?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  updated_at: string;
  messages: Msg[];
}

const keyOf = (symbol: string) => `w3ex_chat_sessions_${symbol}`;

export function loadSessions(symbol: string): ChatSession[] {
  try {
    const raw = localStorage.getItem(keyOf(symbol));
    const arr = raw ? (JSON.parse(raw) as ChatSession[]) : [];
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

export function saveSessions(symbol: string, sessions: ChatSession[]): void {
  try {
    // 每会话最多 40 条消息，最多保留 20 个会话
    const trimmed = sessions
      .slice(0, 20)
      .map((s) => ({ ...s, messages: s.messages.slice(-40) }));
    localStorage.setItem(keyOf(symbol), JSON.stringify(trimmed));
  } catch {
    /* 存储满忽略 */
  }
}

export function newSession(): ChatSession {
  return {
    id: crypto.randomUUID(),
    title: "",
    updated_at: new Date().toISOString(),
    messages: [],
  };
}

export function deleteSession(symbol: string, id: string): ChatSession[] {
  const next = loadSessions(symbol).filter((s) => s.id !== id);
  saveSessions(symbol, next);
  return next;
}

export function autoTitle(messages: Msg[]): string {
  const first = messages.find((m) => m.role === "user");
  if (!first) return "";
  return first.content.length > 24 ? `${first.content.slice(0, 24)}…` : first.content;
}
