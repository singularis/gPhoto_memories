import { useEffect, useRef } from 'react';

/** Rendered as a manual popover so it shows above open dialogs (both live in the top layer). */
export function Toast({ message, onDone }: { message: string | null; onDone: () => void }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !message) return;
    if (el.matches(':popover-open')) el.hidePopover();
    el.showPopover();
    const timer = window.setTimeout(() => {
      el.hidePopover();
      onDone();
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [message, onDone]);

  return (
    <div
      ref={ref}
      popover="manual"
      role="status"
      className="inset-auto bottom-[calc(5.5rem+env(safe-area-inset-bottom))] left-1/2 m-0 max-w-[min(100%-2rem,32rem)] -translate-x-1/2 animate-fade-up rounded-2xl border-0 bg-fg px-5 py-3 text-sm text-bg shadow-2xl sm:bottom-8"
    >
      {message}
    </div>
  );
}
