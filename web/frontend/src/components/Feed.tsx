import { ChevronLeft, ChevronRight, CloudOff, ImageOff } from 'lucide-react';
import type { MediaItem } from '../lib/api';
import { formatDayMonth, formatRelativeDay, plural, yearsAgo } from '../lib/dates';
import { PhotoTile } from './PhotoTile';
import { VideoTile } from './VideoTile';
import { Button } from './ui';

const container = 'mx-auto w-full max-w-screen-2xl px-4 sm:px-8';
const grid =
  'photo-grid grid grid-cols-[repeat(auto-fill,minmax(min(var(--spacing-tile),100%),1fr))] gap-2 max-sm:gap-0.5';

export function Hero({ date, isToday, stats }: { date: string; isToday: boolean; stats?: string }) {
  return (
    <div className={`${container} pt-8 pb-2 sm:pt-12`}>
      <p className="text-sm font-medium text-accent">{isToday ? 'On this day' : formatRelativeDay(date)}</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight text-balance sm:text-3xl">{formatDayMonth(date)}</h1>
      <p className="mt-2 min-h-[1.5em] text-sm text-fg-subtle">
        {stats ?? <span className="inline-block h-[1em] w-48 animate-pulse rounded bg-surface-2 align-middle" />}
      </p>
    </div>
  );
}

export interface YearGroup {
  year: number;
  photos: MediaItem[];
  videos: MediaItem[];
  /** Index of this year's first photo in the flattened lightbox list. */
  offset: number;
}

export function YearSection({
  group,
  viewYear,
  totalPhotos,
  onOpen,
  onRotate,
}: {
  group: YearGroup;
  viewYear: number;
  totalPhotos: number;
  onOpen: (index: number) => void;
  onRotate: (item: MediaItem) => Promise<void>;
}) {
  const { year, photos, videos, offset } = group;
  const headingId = `year-${year}`;
  const counts = [photos.length && plural(photos.length, 'photo'), videos.length && plural(videos.length, 'video')]
    .filter(Boolean)
    .join(' · ');

  return (
    <section aria-labelledby={headingId} className={`${container} pb-8 max-sm:px-0.5 max-sm:pb-4`}>
      <header className="sticky top-[var(--header-h,4rem)] z-10 -mx-4 mb-3 flex flex-wrap items-baseline gap-x-3 bg-bg/85 px-4 py-3 backdrop-blur-md sm:-mx-8 sm:px-8 max-sm:mx-0 max-sm:mb-1 max-sm:px-3.5">
        <h2 id={headingId} className="text-lg font-semibold tabular-nums">
          {year}
        </h2>
        <span className="text-sm text-fg-subtle">{yearsAgo(viewYear, year)}</span>
        <span className="ml-auto text-xs text-fg-subtle">{counts}</span>
      </header>
      <ul role="list" className={grid}>
        {photos.map((item, i) => (
          <PhotoTile
            key={item.path}
            item={item}
            index={offset + i}
            label={`Open photo ${offset + i + 1} of ${totalPhotos}, from ${year}`}
            onOpen={onOpen}
            onRotate={onRotate}
          />
        ))}
        {videos.map((item) => (
          <VideoTile key={item.path} item={item} label={`Play video from ${year}`} />
        ))}
      </ul>
    </section>
  );
}

export function FeedSkeleton() {
  return (
    <div className={`${container} pt-4`} aria-hidden>
      <div className="mb-4 h-6 w-32 animate-pulse rounded-lg bg-surface-2" />
      <div className={grid}>
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="aspect-square animate-pulse rounded-xl bg-surface-2 max-sm:rounded-[3px]" />
        ))}
      </div>
    </div>
  );
}

export function EmptyState({ date, onPrev, onNext }: { date: string; onPrev: () => void; onNext: () => void }) {
  return (
    <div className={`${container} grid place-items-center py-20 text-center`}>
      <div className="grid size-20 place-items-center rounded-full bg-surface-2 text-fg-subtle">
        <ImageOff className="size-9" aria-hidden />
      </div>
      <h2 className="mt-5 text-xl font-semibold">No memories on {formatDayMonth(date)}</h2>
      <p className="mt-2 max-w-sm text-sm text-pretty text-fg-subtle">
        Nothing was captured on this day in earlier years. Try a nearby day.
      </p>
      <div className="mt-6 flex gap-3">
        <Button onClick={onPrev}>
          <ChevronLeft className="size-[1.2em]" aria-hidden /> Previous day
        </Button>
        <Button onClick={onNext}>
          Next day <ChevronRight className="size-[1.2em]" aria-hidden />
        </Button>
      </div>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className={`${container} grid place-items-center py-20 text-center`}>
      <div className="grid size-20 place-items-center rounded-full bg-surface-2 text-fg-subtle">
        <CloudOff className="size-9" aria-hidden />
      </div>
      <h2 className="mt-5 text-xl font-semibold">Couldn't load memories</h2>
      <p className="mt-2 max-w-sm text-sm text-fg-subtle">{message}</p>
      <Button variant="solid" className="mt-6" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}
