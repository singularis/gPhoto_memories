import { useCallback, useEffect, useEffectEvent, useLayoutEffect, useMemo, useState } from 'react';
import { keepPreviousData, queryOptions, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchDay, rotatePhoto, type DayResponse, type MediaItem } from './lib/api';
import { addDays, formatDayMonth, formatFullDate, parseISODate, plural, todayISO, yearsAgo } from './lib/dates';
import { useRouteDate } from './hooks/useRouteDate';
import { formatSeconds, stepSeconds, useApplyScales, useSettings } from './hooks/useSettings';
import { useApplyTheme, useResolvedTheme, useThemePref } from './hooks/useTheme';
import { useDayTransition } from './hooks/useDayTransition';
import { TabBar, TopBar } from './components/Header';
import { EmptyState, ErrorState, FeedSkeleton, Hero, YearSection, type YearGroup } from './components/Feed';
import { Lightbox, type PlayDir } from './components/Lightbox';
import { CalendarDialog } from './components/CalendarDialog';
import { SettingsDialog, type SettingsDraft } from './components/SettingsDialog';
import { Toast } from './components/Toast';

const dayQuery = (date: string) =>
  queryOptions({
    queryKey: ['day', date],
    queryFn: ({ signal }) => fetchDay(date, signal),
    staleTime: 5 * 60_000,
  });

/** How many empty days the slideshow skips before giving up. */
const MAX_EMPTY_SKIPS = 21;

export default function App() {
  const queryClient = useQueryClient();
  const [date, navigate] = useRouteDate();
  const [toast, setToast] = useState<string | null>(null);
  const clearToast = useCallback(() => setToast(null), []);

  // ── settings & theme ─────────────────────────────────────
  const { saved, ready: settingsReady, save } = useSettings(setToast);
  const [themePref, saveTheme] = useThemePref();
  const [draft, setDraft] = useState<SettingsDraft | null>(null);
  const appearance = useResolvedTheme(draft?.theme ?? themePref);
  const toggleAppearance = () => {
    const next = appearance === 'dark' ? 'light' : 'dark';
    if (draft) setDraft({ ...draft, theme: next });
    else saveTheme(next);
  };
  const settings = draft?.settings ?? saved;
  useApplyScales(settings);
  useApplyTheme(draft?.theme ?? themePref);

  // ── dialogs & slideshow ──────────────────────────────────
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [lbIndex, setLbIndex] = useState<number | null>(null);
  const [playDir, setPlayDir] = useState<PlayDir>(0);
  const [crossing, setCrossing] = useState<{ dir: 1 | -1; skips: number } | null>(null);
  const lbOpen = lbIndex !== null;

  // ── data ─────────────────────────────────────────────────
  const query = useQuery({ ...dayQuery(date), placeholderData: keepPreviousData });
  const shown = useDayTransition(query.data, !lbOpen);
  const loadingNewDay = query.isFetching && query.isPlaceholderData;

  useEffect(() => {
    if (!query.isSuccess) return;
    for (const d of [-1, 1]) void queryClient.prefetchQuery(dayQuery(addDays(date, d)));
  }, [date, query.isSuccess, queryClient]);

  const { groups, photos } = useMemo(() => groupByYear(shown, settings.year_order), [shown, settings.year_order]);
  const isToday = date === todayISO();
  const viewYear = parseISODate(shown?.date ?? date).getFullYear();

  useEffect(() => {
    document.title = `${formatDayMonth(date)} · Memories`;
  }, [date]);

  useLayoutEffect(() => {
    window.scrollTo({ top: 0 });
  }, [shown?.date]);

  // ── navigation ───────────────────────────────────────────
  const goTo = useCallback((d: string) => navigate(d), [navigate]);
  const goPrev = () => goTo(addDays(date, -1));
  const goNext = () => goTo(addDays(date, 1));
  const goToday = () => goTo(todayISO());

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
      if (document.querySelector('dialog[open]')) return;
      if ((e.target as HTMLElement).closest?.('input, textarea, select, [contenteditable]')) return;
      if (e.key === 'ArrowLeft') navigate(addDays(date, -1));
      else if (e.key === 'ArrowRight') navigate(addDays(date, 1));
      else if (e.key === 't') navigate(todayISO());
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [date, navigate]);

  // ── photo actions ────────────────────────────────────────
  const rotate = useCallback(
    async (item: MediaItem) => {
      try {
        const res = await rotatePhoto(item);
        const v = res.v ?? Date.now();
        queryClient.setQueriesData<DayResponse>({ queryKey: ['day'] }, (old) =>
          old && {
            ...old,
            media: { ...old.media, images: old.media.images.map((i) => (i.path === item.path ? { ...i, v } : i)) },
          },
        );
      } catch (error) {
        setToast(`Couldn't rotate photo: ${(error as Error).message}`);
      }
    },
    [queryClient],
  );

  const openPhoto = useCallback((index: number) => setLbIndex(index), []);

  const closeLightbox = useCallback(() => {
    setLbIndex(null);
    setPlayDir(0);
    setCrossing(null);
  }, []);

  const step = (delta: 1 | -1) => {
    setPlayDir(0);
    setCrossing(null);
    setLbIndex((i) => (i === null ? i : Math.min(photos.length - 1, Math.max(0, i + delta))));
  };

  const togglePlay = (dir: 1 | -1) => {
    setCrossing(null);
    setPlayDir((current) => (current === dir ? 0 : dir));
  };

  const changeSpeed = (dir: 1 | -1) => save({ ...saved, play_seconds: stepSeconds(saved.play_seconds, dir) });

  // ── slideshow: advance, and roll into the next/previous day at the end ──
  const tick = useEffectEvent(() => {
    if (crossing || lbIndex === null || playDir === 0) return;
    const next = lbIndex + playDir;
    if (next >= 0 && next < photos.length) {
      setLbIndex(next);
      return;
    }
    setCrossing({ dir: playDir, skips: 0 });
    navigate(addDays(date, playDir), { replace: true });
  });

  useEffect(() => {
    if (!lbOpen || playDir === 0) return;
    const id = window.setInterval(tick, settings.play_seconds * 1000);
    return () => window.clearInterval(id);
  }, [lbOpen, playDir, settings.play_seconds]);

  useEffect(() => {
    if (!crossing) return;
    if (query.isError) {
      setCrossing(null);
      setPlayDir(0);
      return;
    }
    if (shown?.date !== date) return;
    if (photos.length) {
      setCrossing(null);
      setLbIndex(crossing.dir > 0 ? 0 : photos.length - 1);
    } else if (crossing.skips < MAX_EMPTY_SKIPS) {
      setCrossing({ ...crossing, skips: crossing.skips + 1 });
      navigate(addDays(date, crossing.dir), { replace: true });
    } else {
      setCrossing(null);
      setPlayDir(0);
    }
  }, [crossing, shown, date, photos.length, query.isError, navigate]);

  const lbPhoto = crossing || lbIndex === null ? undefined : photos[lbIndex];

  // ── settings dialog ──────────────────────────────────────
  const openSettings = () => setDraft({ settings: saved, theme: themePref });
  const saveDraft = () => {
    if (!draft) return;
    save(draft.settings);
    saveTheme(draft.theme);
    setDraft(null);
  };

  const stats = shown
    ? [
        plural(shown.media.images.length, 'photo'),
        plural(shown.media.videos.length, 'video'),
        `${plural(shown.years_found.length, 'year')} of memories`,
      ].join(' · ')
    : undefined;

  const nav = { date, isToday, onPrev: goPrev, onNext: goNext, onToday: goToday, onOpenCalendar: () => setCalendarOpen(true) };

  return (
    <>
      <a
        href="#feed"
        className="sr-only z-50 rounded-full bg-accent px-4 py-2 text-accent-fg focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to photos
      </a>

      <TopBar {...nav} onOpenSettings={openSettings} appearance={appearance} onToggleAppearance={toggleAppearance} />

      {loadingNewDay && (
        <div
          role="progressbar"
          aria-label="Loading day"
          className="fixed inset-x-0 top-[var(--header-h,4rem)] z-40 h-0.5 overflow-hidden"
        >
          <div className="h-full w-2/5 animate-progress rounded-full bg-accent" />
        </div>
      )}

      <main
        id="feed"
        tabIndex={-1}
        aria-busy={loadingNewDay || !shown}
        className="pb-16 outline-none max-sm:pb-[calc(6rem+env(safe-area-inset-bottom))]"
      >
        <Hero date={date} isToday={isToday} stats={shown?.date === date ? stats : undefined} />

        <div className={loadingNewDay ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
          {!settingsReady || (!shown && query.isPending) ? (
            <FeedSkeleton />
          ) : !shown && query.isError ? (
            <ErrorState message={query.error.message} onRetry={() => void query.refetch()} />
          ) : shown && groups.length === 0 ? (
            <EmptyState date={shown.date} onPrev={goPrev} onNext={goNext} />
          ) : (
            groups.map((g) => (
              <YearSection
                key={`${shown?.date}-${g.year}`}
                group={g}
                viewYear={viewYear}
                totalPhotos={photos.length}
                onOpen={openPhoto}
                onRotate={rotate}
              />
            ))
          )}
        </div>
      </main>

      <TabBar {...nav} />

      <Lightbox
        open={lbOpen}
        photo={lbPhoto}
        index={lbIndex ?? 0}
        count={crossing ? 0 : photos.length}
        title={crossing ? (crossing.dir > 0 ? 'Next day…' : 'Previous day…') : lbPhoto ? formatFullDate(lbPhoto.date) : ''}
        subtitle={lbPhoto ? yearsAgo(viewYear, lbPhoto.year) : formatDayMonth(date)}
        playDir={playDir}
        seconds={saved.play_seconds}
        appearance={appearance}
        onToggleAppearance={toggleAppearance}
        onStep={step}
        onClose={closeLightbox}
        onPlay={togglePlay}
        onSpeed={changeSpeed}
        onRotate={rotate}
      />

      <CalendarDialog
        open={calendarOpen}
        value={date}
        onClose={() => setCalendarOpen(false)}
        onSelect={(d) => {
          setCalendarOpen(false);
          goTo(d);
        }}
      />

      {draft && (
        <SettingsDialog open draft={draft} onChange={setDraft} onSave={saveDraft} onCancel={() => setDraft(null)} />
      )}

      <Toast message={toast} onDone={clearToast} />
      <span className="sr-only" aria-live="polite">
        {playDir !== 0 ? `Slideshow playing, ${formatSeconds(saved.play_seconds)} per photo` : ''}
      </span>
    </>
  );
}

function groupByYear(day: DayResponse | undefined, order: 'newer' | 'older') {
  if (!day) return { groups: [] as YearGroup[], photos: [] as MediaItem[] };
  const years = [...day.years_found].sort((a, b) => (order === 'older' ? a - b : b - a));
  const groups: YearGroup[] = [];
  const photos: MediaItem[] = [];
  for (const year of years) {
    const yearPhotos = day.media.images.filter((i) => i.year === year);
    const yearVideos = day.media.videos.filter((v) => v.year === year);
    if (!yearPhotos.length && !yearVideos.length) continue;
    groups.push({ year, photos: yearPhotos, videos: yearVideos, offset: photos.length });
    photos.push(...yearPhotos);
  }
  return { groups, photos };
}
