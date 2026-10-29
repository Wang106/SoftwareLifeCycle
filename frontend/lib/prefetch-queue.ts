// A finite admission queue, not a database/request cancellation mechanism.
// Only anonymous read-only, bounded catalog routes are admitted. Never add
// identity/command/detail routes or user-provided URLs/query strings here.
export const PREFETCH_ROUTES = ['/changes', '/issues'] as const;
export function createPrefetchQueue(schedule: (run: () => void) => () => void, admit: (href: string) => void) {
  const sent = new Set<string>();
  let generation = 0;
  let cancel: (() => void) | undefined;
  function pause() { generation++; cancel?.(); cancel = undefined; }
  function dashboardReady(pathname: string, visible = true) {
    if (!visible || pathname !== '/' || cancel || sent.size === PREFETCH_ROUTES.length) return;
    const current = generation;
    function next() {
      const href = PREFETCH_ROUTES.find(route => !sent.has(route));
      if (!href) return;
      cancel = schedule(() => {
        if (current !== generation) return;
        cancel = undefined;
        sent.add(href);
        admit(href);
        next();
      });
    }
    next();
  }
  return { dashboardReady, pause };
}

// The budget limits route admissions, not framework/internal HTTP attempts.
// Expiring eligibility prevents permanent hover/visibility/cache re-warming.
export function createPrefetchWindows(scheduleExpiry: (run: () => void) => () => void, publish: (routes: string[]) => void) {
  const active = new Map<string, () => void>();
  let generation = 0;
  function clear(notify = true) {
    generation++;
    for (const cancel of active.values()) cancel();
    active.clear();
    if (notify) publish([]);
  }
  function admit(href: string) {
    if (!PREFETCH_ROUTES.some(route => route === href) || active.has(href)) return;
    const current = generation;
    const cancel = scheduleExpiry(() => {
      if (current !== generation) return;
      active.delete(href);
      publish([...active.keys()]);
    });
    active.set(href, cancel);
    publish([...active.keys()]);
  }
  return { admit, clear };
}
