import { useCallback, useEffect, useState } from 'react';
import { isValidISODate, todayISO } from '../lib/dates';

/** `/` is always today; any other day lives at `/date/YYYY-MM-DD`. */
function dateFromLocation() {
  const match = /^\/date\/(\d{4}-\d{2}-\d{2})\/?$/.exec(window.location.pathname);
  return match?.[1] && isValidISODate(match[1]) ? match[1] : todayISO();
}

export function useRouteDate() {
  const [date, setDate] = useState(dateFromLocation);

  useEffect(() => {
    const onPop = () => setDate(dateFromLocation());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const navigate = useCallback((next: string, { replace = false } = {}) => {
    const url = next === todayISO() ? '/' : `/date/${next}`;
    if (url !== window.location.pathname) {
      if (replace) window.history.replaceState(null, '', url);
      else window.history.pushState(null, '', url);
    }
    setDate(next);
  }, []);

  return [date, navigate] as const;
}
