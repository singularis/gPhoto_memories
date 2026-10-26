import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { ChevronLeft, ChevronRight, LoaderCircle, Minus, Moon, Pause, Play, Plus, RotateCw, Sun, X } from 'lucide-react';
import type { MediaItem } from '../lib/api';
import { fullUrl, loadedThumbs, mediaKey } from '../lib/media';
import { formatSeconds } from '../hooks/useSettings';
import { Dialog, cn } from './ui';

export type PlayDir = -1 | 0 | 1;

interface Props {
  open: boolean;
  /** Photo to show; undefined while the slideshow is switching days (the last frame stays up). */
  photo: MediaItem | undefined;
  index: number;
  count: number;
  title: string;
  subtitle: string;
  playDir: PlayDir;
  seconds: number;
  appearance: 'light' | 'dark';
  onToggleAppearance: () => void;
  onStep: (delta: 1 | -1) => void;
  onClose: () => void;
  onPlay: (dir: 1 | -1) => void;
  onSpeed: (dir: 1 | -1) => void;
  onRotate: (item: MediaItem) => Promise<void>;
}

const SWIPE_PX = 50;
const IDLE_MS = 2500;
const MANUAL_FADE_MS = 260;

/** Long enough to ease the cut, short enough to finish before the next photo. */
function fadeMs(seconds: number) {
  return Math.round(Math.min(700, Math.max(140, seconds * 1000 * 0.6)));
}

interface Slide {
  current?: string;
  /** Small copy used only for the blurred backdrop. Stays on the thumbnail so the blur stays cheap. */
  blur?: string;
  previous?: string;
  previousBlur?: string;
  ms: number;
}

const glass = 'grid place-items-center rounded-full bg-white/12 text-white backdrop-blur-md transition hover:bg-white/25 active:scale-95 disabled:opacity-30';

export function Lightbox(props: Props) {
  const { open, photo, index, count, playDir, onStep, onPlay } = props;
  const [frame, setFrame] = useState<{ key: string; src: string } | null>(null);
  const [sharp, setSharp] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [idle, setIdle] = useState(false);
  const idleTimer = useRef<number>(undefined);
  const swipe = useRef<{ x: number; y: number } | null>(null);
  const suppressClick = useRef(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const seenKey = useRef<string | null>(null);
  const currentRef = useRef<string | undefined>(undefined);
  const blurRef = useRef<string | undefined>(undefined);
  const [slide, setSlide] = useState<Slide>({ ms: 0 });

  // Rotate comes first in the DOM; start on Close so a stray Enter never rewrites a photo.
  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open]);

  // Open on the thumbnail already on screen, then swap in the screen-sized copy once decoded.
  const photoKey = photo && mediaKey(photo);
  useEffect(() => {
    if (!open || !photo || !photoKey) return;
    const key = photoKey;
    const thumb = loadedThumbs.get(key);
    if (thumb) setFrame({ key, src: thumb });
    setSharp(false);

    let cancelled = false;
    const full = new Image();
    full.src = fullUrl(photo);
    full
      .decode()
      .then(() => {
        if (cancelled) return;
        setFrame({ key, src: full.src });
        setSharp(true);
      })
      .catch(() => {
        if (!cancelled && !thumb) setSharp(true);
      });
    return () => {
      cancelled = true;
    };
  }, [open, photoKey]);

  useEffect(() => {
    if (!open) setFrame(null);
  }, [open]);

  // Crossfade when the photo changes. Upgrading the same photo from thumbnail to full size does not.
  useEffect(() => {
    if (!open) {
      seenKey.current = null;
      currentRef.current = undefined;
      blurRef.current = undefined;
      setSlide({ ms: 0 });
      return;
    }
    if (!frame) return;

    if (seenKey.current === frame.key) {
      currentRef.current = frame.src;
      setSlide((prev) => ({ ...prev, current: frame.src }));
      return;
    }

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const ms = seenKey.current && !reduce ? (playDir !== 0 ? fadeMs(props.seconds) : MANUAL_FADE_MS) : 0;
    const previous = ms ? currentRef.current : undefined;
    const previousBlur = ms ? blurRef.current : undefined;
    seenKey.current = frame.key;
    currentRef.current = frame.src;
    blurRef.current = frame.src;
    setSlide({ current: frame.src, blur: frame.src, previous, previousBlur, ms });
  }, [open, frame, playDir, props.seconds]);

  useEffect(() => {
    if (!slide.previous || !slide.ms) return;
    const timer = window.setTimeout(
      () => setSlide((prev) => ({ ...prev, previous: undefined, previousBlur: undefined })),
      slide.ms,
    );
    return () => window.clearTimeout(timer);
  }, [slide.previous, slide.ms]);

  // While a slideshow runs, controls fade away until the pointer moves.
  const wake = () => {
    setIdle(false);
    window.clearTimeout(idleTimer.current);
    if (playDir !== 0) idleTimer.current = window.setTimeout(() => setIdle(true), IDLE_MS);
  };
  useEffect(() => {
    wake();
    return () => window.clearTimeout(idleTimer.current);
  }, [playDir, open]);

  const onKeyDown = (e: KeyboardEvent) => {
    wake();
    if (e.key === 'ArrowRight') onStep(1);
    else if (e.key === 'ArrowLeft') onStep(-1);
    else if (e.key === ' ' && (e.target as HTMLElement).tagName !== 'BUTTON') onPlay(1);
    else return;
    e.preventDefault();
  };

  const onPointerDown = (e: PointerEvent) => {
    swipe.current = { x: e.clientX, y: e.clientY };
    if (idle) {
      suppressClick.current = true;
      wake();
    }
  };
  const onPointerUp = (e: PointerEvent) => {
    const start = swipe.current;
    swipe.current = null;
    if (!start) return;
    const dx = e.clientX - start.x;
    if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > Math.abs(e.clientY - start.y)) {
      suppressClick.current = true;
      onStep(dx < 0 ? 1 : -1);
    }
  };
  const onStageClick = () => {
    if (suppressClick.current) {
      suppressClick.current = false;
      return;
    }
    props.onClose();
  };

  const rotate = async () => {
    if (!photo) return;
    setRotating(true);
    try {
      await props.onRotate(photo);
    } finally {
      setRotating(false);
    }
  };

  const chrome = cn('transition-opacity duration-300', idle && 'pointer-events-none opacity-0');

  return (
    <Dialog
      open={open}
      onClose={props.onClose}
      aria-label="Photo viewer"
      className="m-0 h-dvh max-h-none w-dvw max-w-none overflow-hidden bg-black p-0 text-white backdrop:bg-black"
    >
      <div
        className={cn('relative size-full', idle && 'cursor-none')}
        onKeyDown={onKeyDown}
        onPointerMove={wake}
      >
        <div className="pointer-events-none absolute inset-0 overflow-hidden bg-black" aria-hidden>
          {slide.previousBlur && (
            <img
              src={slide.previousBlur}
              alt=""
              className="lb-fade-out absolute inset-0 size-full scale-125 object-cover blur-3xl"
              style={{ animationDuration: `${slide.ms}ms` }}
            />
          )}
          {slide.blur && (
            <img
              src={slide.blur}
              alt=""
              className={cn('absolute inset-0 size-full scale-125 object-cover blur-3xl', slide.ms > 0 && 'lb-fade-in')}
              style={slide.ms > 0 ? { animationDuration: `${slide.ms}ms` } : undefined}
            />
          )}
          <div className="absolute inset-0 bg-black/40" />
        </div>

        <div
          className="relative grid size-full touch-pan-y place-items-center select-none"
          onPointerDown={onPointerDown}
          onPointerUp={onPointerUp}
          onPointerCancel={() => (swipe.current = null)}
          onClick={onStageClick}
        >
          {slide.previous && (
            <img
              src={slide.previous}
              alt=""
              aria-hidden
              draggable={false}
              className="lb-fade-out pointer-events-none absolute inset-0 m-auto max-h-dvh max-w-full object-contain sm:max-h-[94dvh] sm:max-w-[94vw] sm:rounded-lg"
              style={{ animationDuration: `${slide.ms}ms` }}
            />
          )}
          {slide.current && (
            <img
              src={slide.current}
              alt={props.title}
              draggable={false}
              className={cn(
                'absolute inset-0 m-auto max-h-dvh max-w-full object-contain shadow-2xl sm:max-h-[94dvh] sm:max-w-[94vw] sm:rounded-lg',
                slide.ms > 0 && 'lb-fade-in',
              )}
              style={slide.ms > 0 ? { animationDuration: `${slide.ms}ms` } : undefined}
            />
          )}
        </div>

        {!sharp && (
          <span className="pointer-events-none absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 animate-delayed-in">
            <LoaderCircle className="size-8 animate-spin text-white/70" aria-label="Loading photo" />
          </span>
        )}

        <div
          className={cn(
            'absolute inset-x-0 top-0 flex items-start gap-3 bg-gradient-to-b from-black/65 to-transparent px-3 pt-[max(0.75rem,env(safe-area-inset-top))] pb-10 sm:px-5',
            chrome,
          )}
        >
          <div className="min-w-0 pt-1.5 pl-1" aria-live="polite">
            <p className="truncate text-base font-semibold">{props.title}</p>
            <p className="text-sm text-white/70 tabular-nums">
              {props.subtitle}
              {count > 0 && photo && ` · ${index + 1} / ${count}`}
            </p>
          </div>
          <div className="ml-auto flex shrink-0 gap-2">
            <button
              type="button"
              className={cn(glass, 'size-11')}
              onClick={props.onToggleAppearance}
              aria-label={props.appearance === 'dark' ? 'Switch to light appearance' : 'Switch to dark appearance'}
              title={props.appearance === 'dark' ? 'Light appearance' : 'Dark appearance'}
            >
              {props.appearance === 'dark' ? <Sun className="size-5" aria-hidden /> : <Moon className="size-5" aria-hidden />}
            </button>
            <button type="button" className={cn(glass, 'size-11')} onClick={rotate} disabled={rotating || !photo} aria-label="Rotate photo clockwise" title="Rotate clockwise">
              {rotating ? <LoaderCircle className="size-5 animate-spin" aria-hidden /> : <RotateCw className="size-5" aria-hidden />}
            </button>
            <button ref={closeRef} type="button" className={cn(glass, 'size-11')} onClick={props.onClose} aria-label="Close viewer" title="Close (Esc)">
              <X className="size-5" aria-hidden />
            </button>
          </div>
        </div>

        <button
          type="button"
          className={cn(glass, 'absolute top-1/2 left-4 size-14 -translate-y-1/2 max-sm:hidden', chrome)}
          onClick={() => onStep(-1)}
          disabled={index <= 0}
          aria-label="Previous photo (←)"
        >
          <ChevronLeft className="size-7" aria-hidden />
        </button>
        <button
          type="button"
          className={cn(glass, 'absolute top-1/2 right-4 size-14 -translate-y-1/2 max-sm:hidden', chrome)}
          onClick={() => onStep(1)}
          disabled={index >= count - 1}
          aria-label="Next photo (→)"
        >
          <ChevronRight className="size-7" aria-hidden />
        </button>

        <div
          className={cn(
            'absolute inset-x-0 bottom-0 flex justify-center bg-gradient-to-t from-black/65 to-transparent px-3 pt-12 pb-[max(1.25rem,env(safe-area-inset-bottom))]',
            chrome,
          )}
        >
          <div role="group" aria-label="Slideshow" className="flex items-center gap-2 rounded-full bg-black/40 p-1.5 backdrop-blur-md">
            <button type="button" className={cn(glass, 'size-10')} onClick={() => props.onSpeed(-1)} aria-label="Faster (shorter delay)" title="Faster">
              <Minus className="size-4" aria-hidden />
            </button>
            <span className="min-w-12 text-center text-sm font-semibold tabular-nums" aria-label={`${formatSeconds(props.seconds)} per photo`}>
              {formatSeconds(props.seconds)}
            </span>
            <button type="button" className={cn(glass, 'size-10')} onClick={() => props.onSpeed(1)} aria-label="Slower (longer delay)" title="Slower">
              <Plus className="size-4" aria-hidden />
            </button>
            <span className="mx-1 h-6 w-px bg-white/20" aria-hidden />
            <PlayButton active={playDir === -1} reverse onClick={() => onPlay(-1)} />
            <PlayButton active={playDir === 1} onClick={() => onPlay(1)} />
          </div>
        </div>
      </div>
    </Dialog>
  );
}

function PlayButton({ active, reverse, onClick }: { active: boolean; reverse?: boolean; onClick: () => void }) {
  const label = active ? 'Pause slideshow' : reverse ? 'Play slideshow backwards' : 'Play slideshow';
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-pressed={active}
      title={label}
      className={cn(
        'grid size-12 place-items-center rounded-full transition active:scale-95',
        active ? 'bg-accent text-accent-fg' : 'bg-white/12 text-white hover:bg-white/25',
      )}
    >
      {active ? (
        <Pause className="size-5 fill-current" aria-hidden />
      ) : (
        <Play className={cn('size-5 fill-current', reverse ? 'mr-0.5 rotate-180' : 'ml-0.5')} aria-hidden />
      )}
    </button>
  );
}
