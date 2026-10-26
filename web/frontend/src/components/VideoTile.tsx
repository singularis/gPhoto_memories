import { useState } from 'react';
import { Play, Video } from 'lucide-react';
import type { MediaItem } from '../lib/api';
import { mediaUrl } from '../lib/media';

/** Videos stay a lightweight card until tapped; we never download clips nobody watches. */
export function VideoTile({ item, label }: { item: MediaItem; label: string }) {
  const [playing, setPlaying] = useState(false);

  return (
    <li className="relative aspect-square animate-fade-up overflow-hidden rounded-xl bg-stone-900 max-sm:rounded-[3px]">
      {playing ? (
        <video controls autoPlay playsInline className="size-full bg-black object-contain">
          {/* Explicit mp4 type lets Chrome try H.264 .mov files it would otherwise refuse. */}
          <source src={mediaUrl(item)} type="video/mp4" />
        </video>
      ) : (
        <button
          type="button"
          onClick={() => setPlaying(true)}
          aria-label={label}
          className="group grid size-full place-items-center bg-gradient-to-br from-stone-700 via-stone-800 to-stone-950 focus-visible:outline-offset-[-3px]"
        >
          <span className="grid size-16 place-items-center rounded-full bg-white/92 text-stone-900 shadow-lg transition group-hover:scale-110 max-sm:size-11">
            <Play className="ml-0.5 size-6 fill-current max-sm:size-4" aria-hidden />
          </span>
          <span className="absolute top-2.5 right-2.5 inline-flex items-center gap-1 rounded-md bg-black/45 px-2 py-1 text-xs font-medium tracking-wide text-white backdrop-blur max-sm:top-1 max-sm:right-1 max-sm:px-1.5">
            <Video className="size-[1.1em]" aria-hidden />
            <span className="max-sm:sr-only">Video</span>
          </span>
        </button>
      )}
    </li>
  );
}
