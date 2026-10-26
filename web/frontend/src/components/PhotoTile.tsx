import { memo, useEffect, useRef, useState } from 'react';
import { ImageOff, LoaderCircle, RotateCw } from 'lucide-react';
import type { MediaItem } from '../lib/api';
import { loadedThumbs, mediaKey, thumbUrl } from '../lib/media';
import { enqueueThumb, type QueueTicket } from '../lib/thumbQueue';
import { cn } from './ui';

interface Props {
  item: MediaItem;
  index: number;
  label: string;
  onOpen: (index: number) => void;
  onRotate: (item: MediaItem) => Promise<void>;
}

export const PhotoTile = memo(function PhotoTile({ item, index, label, onOpen, onRotate }: Props) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const ticket = useRef<QueueTicket | null>(null);
  const srcRef = useRef<string | undefined>(undefined);
  const [src, setSrc] = useState<string>();
  const [status, setStatus] = useState<'loading' | 'loaded' | 'error'>('loading');
  const [rotating, setRotating] = useState(false);
  const key = mediaKey(item);

  useEffect(() => {
    const el = buttonRef.current;
    if (!el) return;
    const t = enqueueThumb(() => {
      const url = thumbUrl(item, el.clientWidth);
      if (url === srcRef.current) return t.finish();
      srcRef.current = url;
      setSrc(url);
    });
    ticket.current = t;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          t.prioritize();
          observer.disconnect();
        }
      },
      { rootMargin: '600px 0px' },
    );
    observer.observe(el);
    return () => {
      observer.disconnect();
      t.cancel();
    };
    // `key` covers path + version, so a rotation reloads the thumbnail.
  }, [key]);

  const settle = (next: 'loaded' | 'error') => {
    setStatus(next);
    if (next === 'loaded' && src) loadedThumbs.set(key, src);
    ticket.current?.finish();
  };

  const rotate = async () => {
    setRotating(true);
    try {
      await onRotate(item);
    } finally {
      setRotating(false);
    }
  };

  return (
    <li
      className="group relative aspect-square animate-fade-up overflow-hidden rounded-xl bg-surface-2 max-sm:rounded-[3px]"
      style={{ animationDelay: `${Math.min(index, 12) * 25}ms` }}
    >
      <button
        ref={buttonRef}
        type="button"
        onClick={() => onOpen(index)}
        aria-label={label}
        className="absolute inset-0 size-full cursor-zoom-in focus-visible:outline-offset-[-3px]"
      >
        {status === 'loading' && <span className="absolute inset-0 animate-pulse bg-surface-2" />}
        {status === 'error' && (
          <span className="absolute inset-0 grid place-items-center text-fg-subtle">
            <ImageOff className="size-[1.5em]" aria-hidden />
          </span>
        )}
        {src && (
          <img
            src={src}
            alt=""
            decoding="async"
            draggable={false}
            onLoad={() => settle('loaded')}
            onError={() => settle('error')}
            className={cn(
              'size-full object-cover transition duration-500 ease-out group-hover:scale-[1.04] group-hover:brightness-105',
              status === 'loaded' ? 'opacity-100' : 'opacity-0',
            )}
          />
        )}
      </button>
      <button
        type="button"
        onClick={rotate}
        disabled={rotating}
        aria-label="Rotate photo clockwise"
        title="Rotate clockwise"
        className="absolute right-2 bottom-2 grid size-10 place-items-center rounded-full bg-white/85 text-stone-800 opacity-0 shadow-md backdrop-blur transition group-hover:opacity-100 group-focus-within:opacity-100 hover:scale-110 hover:bg-white disabled:opacity-100 pointer-coarse:opacity-80 max-sm:right-1 max-sm:bottom-1 max-sm:size-8"
      >
        {rotating ? (
          <LoaderCircle className="size-4 animate-spin" aria-hidden />
        ) : (
          <RotateCw className="size-4" aria-hidden />
        )}
      </button>
    </li>
  );
});
