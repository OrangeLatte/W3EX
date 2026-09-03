const KEY = "w3ex_user_key";

/** 需求⑥：浏览器级用户标识（模拟交易账户隔离），首次访问生成并持久化。 */
export function getOrCreateUserKey(): string {
  if (typeof window === "undefined") return "default";
  let k = window.localStorage.getItem(KEY);
  if (!k) {
    k = crypto.randomUUID();
    window.localStorage.setItem(KEY, k);
  }
  return k;
}
