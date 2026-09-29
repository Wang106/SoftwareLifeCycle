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

export async function apiGet<T>(path: string): Promise<T | null> {
  await connection();
  if (!API_BASE) return null;
  try {
    const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json() as T;
  } catch {
    return null;
  }
}
