import { useEffect, useMemo, useState, type KeyboardEvent } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { addDays, firstDayOfWeek, formatFullDate, formatMonthYear, parseISODate, toISODate, todayISO } from '../lib/dates';
import { Button, IconButton, SheetDialog, cn } from './ui';

const weekdayFmt = new Intl.DateTimeFormat(undefined, { weekday: 'short' });
const KEY_STEPS: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };

export function CalendarDialog({
  open,
  value,
  onSelect,
  onClose,
}: {
  open: boolean;
  value: string;
  onSelect: (iso: string) => void;
  onClose: () => void;
}) {
  const [month, setMonth] = useState(() => monthStart(value));
  const [focusIso, setFocusIso] = useState<string | null>(null);
  const today = todayISO();
  const weekStart = useMemo(firstDayOfWeek, []);

  useEffect(() => {
    if (!open) return;
    setMonth(monthStart(value));
    setFocusIso(value);
  }, [open, value]);

  useEffect(() => {
    if (!focusIso) return;
    document.querySelector<HTMLButtonElement>(`[data-iso="${focusIso}"]`)?.focus();
    setFocusIso(null);
  }, [focusIso, month]);

  const weekdays = useMemo(() => {
    const sunday = new Date(2024, 0, 7);
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(sunday);
      d.setDate(sunday.getDate() + ((weekStart + i) % 7));
      return weekdayFmt.format(d);
    });
  }, [weekStart]);

  const cells = useMemo(() => {
    const lead = (month.getDay() - weekStart + 7) % 7;
    const days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
    return [
      ...Array.from({ length: lead }, () => null),
      ...Array.from({ length: days }, (_, i) => toISODate(new Date(month.getFullYear(), month.getMonth(), i + 1, 12))),
    ];
  }, [month, weekStart]);

  const shiftMonth = (delta: number) => setMonth(new Date(month.getFullYear(), month.getMonth() + delta, 1, 12));

  const onGridKey = (e: KeyboardEvent) => {
    const step = KEY_STEPS[e.key];
    const current = (e.target as HTMLElement).dataset.iso;
    if (!step || !current) return;
    e.preventDefault();
    const next = addDays(current, step);
    const nextMonth = monthStart(next);
    if (nextMonth.getTime() !== month.getTime()) setMonth(nextMonth);
    setFocusIso(next);
  };

  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="Choose a date"
      titleId="calendar-title"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="solid" onClick={() => onSelect(today)}>
            Today
          </Button>
        </>
      }
    >
      <div className="mb-4 flex items-center justify-between">
        <IconButton label="Previous month" onClick={() => shiftMonth(-1)}>
          <ChevronLeft className="size-[1.2em]" aria-hidden />
        </IconButton>
        <p className="text-base font-semibold" aria-live="polite">
          {formatMonthYear(month)}
        </p>
        <IconButton label="Next month" onClick={() => shiftMonth(1)}>
          <ChevronRight className="size-[1.2em]" aria-hidden />
        </IconButton>
      </div>

      <div className="grid grid-cols-7 gap-1 text-center" onKeyDown={onGridKey}>
        {weekdays.map((d) => (
          <div key={d} className="pb-2 text-xs font-medium tracking-wide text-fg-subtle uppercase" aria-hidden>
            {d}
          </div>
        ))}
        {cells.map((iso, i) =>
          iso ? (
            <button
              key={iso}
              type="button"
              data-iso={iso}
              onClick={() => onSelect(iso)}
              aria-label={formatFullDate(iso)}
              aria-current={iso === today ? 'date' : undefined}
              aria-pressed={iso === value}
              tabIndex={iso === value || (!cells.includes(value) && i === cells.findIndex(Boolean)) ? 0 : -1}
              className={cn(
                'aspect-square min-h-11 rounded-full text-sm tabular-nums transition',
                iso === value
                  ? 'bg-accent font-semibold text-accent-fg shadow-sm'
                  : 'hover:bg-surface-2',
                iso === today && iso !== value && 'font-semibold text-accent ring-1 ring-accent/50 ring-inset',
              )}
            >
              {parseISODate(iso).getDate()}
            </button>
          ) : (
            <span key={`pad-${i}`} />
          ),
        )}
      </div>
    </SheetDialog>
  );
}

function monthStart(iso: string) {
  const d = parseISODate(iso);
  return new Date(d.getFullYear(), d.getMonth(), 1, 12);
}
