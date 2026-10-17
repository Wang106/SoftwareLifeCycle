import "server-only";
import { connection } from "next/server";

const configuredApiBase =
  process.env.API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "";

export const API_BASE = configuredApiBase
  .replace(/\/api\/v1\/?$/, "")
  .replace(/\/$/, "");

export async function apiGet<T>(path: string, options?: { timeoutMs: number }): Promise<T | null> {
  await connection();
  if (!API_BASE) return null;
  const timeoutMs = options?.timeoutMs;
  if (timeoutMs !== undefined && (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > 2147483647)) return null;
  const controller = timeoutMs === undefined ? undefined : new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const read = async (): Promise<T | null> => {
      const res = await fetch(`${API_BASE}${path}`, {
        cache: "no-store",
        ...(controller ? { signal: controller.signal } : {}),
      });
      if (!res.ok) return null;
      return await res.json() as T;
    };
    if (timeoutMs === undefined) return await read();
    // Cover response-body reads as well as headers; release the page even if
    // an upstream implementation does not settle promptly after cancellation.
    return await Promise.race([
      new Promise<null>(resolve => {
        timer = setTimeout(() => {
          resolve(null);
          controller!.abort();
        }, timeoutMs);
      }),
      read(),
    ]);
  } catch {
    return null;
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}
