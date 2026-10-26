import { useCallback, useEffect, useState } from 'react';

export type ThemePref = 'system' | 'light' | 'dark';

const STORAGE_KEY = 'theme';
const THEME_COLORS = { light: '#f6f3ee', dark: '#13110f' } as const;

function readPref(): ThemePref {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === 'light' || stored === 'dark' ? stored : 'system';
}

/** Theme is per device (localStorage), unlike the other settings which live on the server. */
export function useThemePref() {
  const [pref, setPref] = useState<ThemePref>(readPref);
  const save = useCallback((next: ThemePref) => {
    localStorage.setItem(STORAGE_KEY, next);
    setPref(next);
  }, []);
  return [pref, save] as const;
}

/** The appearance actually on screen, after resolving "Auto". */
export function useResolvedTheme(pref: ThemePref) {
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia('(prefers-color-scheme: dark)').matches,
  );

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => setSystemDark(media.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  return pref === 'dark' || (pref === 'system' && systemDark) ? 'dark' : 'light';
}

export function useApplyTheme(pref: ThemePref) {
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => {
      const mode = pref === 'dark' || (pref === 'system' && media.matches) ? 'dark' : 'light';
      document.documentElement.dataset.theme = mode;
      document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLORS[mode]);
    };
    apply();
    media.addEventListener('change', apply);
    return () => media.removeEventListener('change', apply);
  }, [pref]);
}
