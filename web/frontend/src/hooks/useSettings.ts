import { useLayoutEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DEFAULT_SETTINGS, fetchSettings, saveSettings, type Settings } from '../lib/api';

const KEY = ['settings'];

export function useSettings(onError: (message: string) => void) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: KEY, queryFn: fetchSettings, staleTime: Infinity, retry: 1 });

  const mutation = useMutation({
    mutationFn: saveSettings,
    onMutate: (next) => {
      const previous = queryClient.getQueryData<Settings>(KEY);
      queryClient.setQueryData(KEY, next);
      return { previous };
    },
    onError: (error, _next, context) => {
      queryClient.setQueryData(KEY, context?.previous);
      onError(`Settings were not saved: ${error.message}`);
    },
  });

  return {
    saved: query.data ?? DEFAULT_SETTINGS,
    ready: !query.isPending,
    save: mutation.mutate,
  };
}

/** Push the size settings into CSS so the grid and type scale without re-rendering. */
export function useApplyScales({ image_scale, font_scale }: Settings) {
  useLayoutEffect(() => {
    const root = document.documentElement.style;
    root.setProperty('--scale', String(image_scale));
    root.setProperty('--font-scale', String(font_scale));
  }, [image_scale, font_scale]);
}

const clampSeconds = (n: number) => Math.round(Math.min(15, Math.max(0.2, n)) * 10) / 10;

/** +1 waits longer (slower), -1 waits less (faster). Below 1s it moves in 0.2s steps. */
export function stepSeconds(current: number, dir: 1 | -1) {
  const next = current < 1 || (dir < 0 && current <= 1) ? current + dir * 0.2 : current + dir;
  return clampSeconds(next);
}

export function formatSeconds(n: number) {
  return `${Number.isInteger(n) ? n : n.toFixed(1)}s`;
}
