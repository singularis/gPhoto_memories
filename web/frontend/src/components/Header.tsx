import { useLayoutEffect, useRef } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight, Moon, Settings2, Sun } from 'lucide-react';
import { formatDayMonth, formatShortDayMonth } from '../lib/dates';
import { Button, IconButton } from './ui';

interface NavProps {
  date: string;
  isToday: boolean;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  onOpenCalendar: () => void;
}

export function TopBar({
  onOpenSettings,
  appearance,
  onToggleAppearance,
  ...nav
}: NavProps & {
  onOpenSettings: () => void;
  appearance: 'light' | 'dark';
  onToggleAppearance: () => void;
}) {
  const ref = useRef<HTMLElement>(null);

  // Sticky year headings sit right under the bar, whose height follows the text size setting.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(() =>
      document.documentElement.style.setProperty('--header-h', `${el.offsetHeight}px`),
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <header
      ref={ref}
      className="sticky top-0 z-30 border-b border-line bg-bg/80 pt-[env(safe-area-inset-top)] backdrop-blur-xl backdrop-saturate-150"
    >
      <div className="mx-auto flex min-h-16 max-w-screen-2xl items-center gap-3 px-4 py-2 sm:px-8">
        <button
          type="button"
          onClick={nav.onToday}
          className="-ml-1 flex items-center gap-3 rounded-full py-1 pr-3 pl-1"
          aria-label="Memories, go to today"
        >
          <img src="/icons/logo-128.webp" alt="" width={36} height={36} className="size-9 rounded-full shadow-sm" />
          <span className="text-lg font-semibold tracking-tight">Memories</span>
        </button>

        <nav aria-label="Change day" className="ml-auto hidden items-center gap-2 sm:flex">
          <IconButton label="Previous day (←)" onClick={nav.onPrev}>
            <ChevronLeft className="size-[1.3em]" aria-hidden />
          </IconButton>
          <Button onClick={nav.onToday} disabled={nav.isToday}>
            Today
          </Button>
          <IconButton label="Next day (→)" onClick={nav.onNext}>
            <ChevronRight className="size-[1.3em]" aria-hidden />
          </IconButton>
          <Button variant="soft" onClick={nav.onOpenCalendar} aria-haspopup="dialog">
            <CalendarDays className="size-[1.2em]" aria-hidden />
            {formatDayMonth(nav.date)}
          </Button>
        </nav>

        <div className="ml-auto flex items-center gap-2 sm:ml-0">
          <AppearanceButton appearance={appearance} onClick={onToggleAppearance} />
          <IconButton label="Settings" onClick={onOpenSettings} aria-haspopup="dialog">
            <Settings2 className="size-[1.25em]" aria-hidden />
          </IconButton>
        </div>
      </div>
    </header>
  );
}

export function AppearanceButton({
  appearance,
  onClick,
  className,
}: {
  appearance: 'light' | 'dark';
  onClick: () => void;
  className?: string;
}) {
  const toDark = appearance === 'light';
  return (
    <IconButton
      label={toDark ? 'Switch to dark appearance' : 'Switch to light appearance'}
      onClick={onClick}
      className={className}
    >
      {toDark ? <Moon className="size-[1.25em]" aria-hidden /> : <Sun className="size-[1.25em]" aria-hidden />}
    </IconButton>
  );
}

/** Thumb-reachable day navigation on phones. */
export function TabBar(nav: NavProps) {
  const item =
    'flex min-h-12 items-center justify-center gap-1.5 rounded-2xl px-2 text-sm font-semibold transition active:bg-accent/12 disabled:opacity-40';
  return (
    <nav
      aria-label="Change day"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-bg/85 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl backdrop-saturate-150 sm:hidden"
    >
      <div className="grid grid-cols-[1fr_1.4fr_1.6fr_1fr] items-center gap-1 px-2 py-1.5">
        <button type="button" className={item} onClick={nav.onPrev} aria-label="Previous day">
          <ChevronLeft className="size-[1.4em]" aria-hidden />
        </button>
        <button type="button" className={item} onClick={nav.onToday} disabled={nav.isToday}>
          Today
        </button>
        <button
          type="button"
          className={`${item} text-accent`}
          onClick={nav.onOpenCalendar}
          aria-haspopup="dialog"
          aria-label={`Choose date, currently ${formatDayMonth(nav.date)}`}
        >
          <CalendarDays className="size-[1.1em] shrink-0" aria-hidden />
          <span className="truncate">{formatShortDayMonth(nav.date)}</span>
        </button>
        <button type="button" className={item} onClick={nav.onNext} aria-label="Next day">
          <ChevronRight className="size-[1.4em]" aria-hidden />
        </button>
      </div>
    </nav>
  );
}
