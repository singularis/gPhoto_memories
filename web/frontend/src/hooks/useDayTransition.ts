import { useEffect, useState } from 'react';
import { flushSync } from 'react-dom';
import type { DayResponse } from '../lib/api';

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * Holds the day currently on screen. Switching to a different day cross-fades with the
 * View Transitions API where supported; same-day updates (e.g. a rotation) apply instantly.
 */
export function useDayTransition(data: DayResponse | undefined, animate: boolean) {
  const [shown, setShown] = useState(data);

  useEffect(() => {
    if (data === shown) return;
    const newDay = !!shown && !!data && data.date !== shown.date;
    if (!newDay || !animate || !document.startViewTransition || reducedMotion()) {
      setShown(data);
      return;
    }
    document.startViewTransition(() => flushSync(() => setShown(data)));
  }, [data, shown, animate]);

  return shown;
}
