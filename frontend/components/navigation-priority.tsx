'use client';
import Link from 'next/link';
import { Localized } from './localized';
import { usePathname } from 'next/navigation';
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { createPrefetchQueue, createPrefetchWindows } from '../lib/prefetch-queue';

const Priority = createContext({ allowed: [] as string[], dashboardReady: () => {} });
function idle(run: () => void) {
  // Defer even on fast machines so a foreground interaction can revoke unsent work.
  let idleId: number | undefined;
  const timer = window.setTimeout(() => {
    if ('requestIdleCallback' in window) idleId = window.requestIdleCallback(run, { timeout: 1500 });
    else run();
  }, 500);
  return () => { window.clearTimeout(timer); if (idleId !== undefined) window.cancelIdleCallback(idleId); };
}
export function NavigationPriorityProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const path = useRef(pathname);
  path.current = pathname;
  const [allowed, setAllowed] = useState<string[]>([]);
  const windows = useRef<ReturnType<typeof createPrefetchWindows> | null>(null);
  if (!windows.current) windows.current = createPrefetchWindows(run => {
    const timer = window.setTimeout(run, 2000);
    return () => window.clearTimeout(timer);
  }, setAllowed);
  const queue = useRef<ReturnType<typeof createPrefetchQueue> | null>(null);
  if (!queue.current) queue.current = createPrefetchQueue(idle, windows.current.admit);
  const pause = useCallback(() => { queue.current!.pause(); windows.current!.clear(); }, []);
  const dashboardReady = useCallback(() => { queue.current!.dashboardReady(path.current, !document.hidden); }, []);
  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = (event.target as Element | null)?.closest?.('a[href]');
      if (!(anchor instanceof HTMLAnchorElement) || anchor.target === '_blank' || anchor.hasAttribute('download')) return;
      const url = new URL(anchor.href, location.href);
      if (url.origin === location.origin && (url.pathname !== location.pathname || url.search !== location.search)) pause();
    }
    function onVisibility() { if (document.hidden) pause(); }
    document.addEventListener('click', onClick, true);
    window.addEventListener('popstate', pause);
    document.addEventListener('visibilitychange', onVisibility);
    return () => { queue.current!.pause(); windows.current!.clear(false); document.removeEventListener('click', onClick, true); window.removeEventListener('popstate', pause); document.removeEventListener('visibilitychange', onVisibility); };
  }, [pause]);
  // Programmatic navigation also revokes unsent work. No shared server data cache,
  // browser API proxy, or cross-user payload cache is introduced.
  useEffect(() => { if (pathname !== '/') pause(); }, [pathname, pause]);
  return <Priority.Provider value={{ allowed, dashboardReady }}><Localized>{children}</Localized></Priority.Provider>;
}
export function DashboardReady() {
  const { dashboardReady } = useContext(Priority);
  useEffect(() => { dashboardReady(); }, [dashboardReady]);
  return null;
}
export function PriorityLink({ href, children, allowBackground = false, ...props }: { href: string; children: React.ReactNode; className?: string; allowBackground?: boolean }) {
  const context = useContext(Priority);
  const allowed = allowBackground ? context.allowed : [];
  // true is intentional: with loading.tsx, automatic prefetch can fetch only a
  // route shell. The two admitted links request full RSC data. All others wait
  // for explicit navigation. Already sent RSC/DB work is not cancelled here.
  return <Link {...props} href={href} prefetch={allowed.includes(href) ? true : false}><Localized>{children}</Localized></Link>;
}
