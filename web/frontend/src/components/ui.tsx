import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { X } from 'lucide-react';

export function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(' ');
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

export function IconButton({ label, className, children, ...rest }: ButtonProps & { label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cn(
        'inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-full border border-line bg-surface p-2 text-sm text-fg shadow-xs transition hover:bg-surface-2 active:scale-95 disabled:opacity-40',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Button({
  variant = 'ghost',
  className,
  ...rest
}: ButtonProps & { variant?: 'ghost' | 'solid' | 'soft' }) {
  return (
    <button
      type="button"
      className={cn(
        'inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 text-sm font-medium whitespace-nowrap transition active:scale-[0.97] disabled:opacity-40',
        variant === 'ghost' && 'border border-line bg-surface text-fg hover:bg-surface-2',
        variant === 'solid' && 'bg-accent text-accent-fg shadow-sm hover:bg-accent-hover',
        variant === 'soft' && 'bg-accent/12 text-accent hover:bg-accent/20',
        className,
      )}
      {...rest}
    />
  );
}

/** Native <dialog> as a modal: focus trap, Esc to close and top-layer rendering come for free. */
export function Dialog({
  open,
  onClose,
  className,
  children,
  ...aria
}: {
  open: boolean;
  onClose: () => void;
  className?: string;
  children: ReactNode;
  'aria-label'?: string;
  'aria-labelledby'?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className={className}
      {...aria}
    >
      {children}
    </dialog>
  );
}

/** Card-style dialog on desktop, bottom sheet on phones. */
export function SheetDialog({
  open,
  onClose,
  title,
  titleId,
  footer,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  titleId: string;
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      aria-labelledby={titleId}
      className="sheet m-auto max-h-[min(92dvh,52rem)] w-[min(100%-2rem,30rem)] overflow-hidden rounded-3xl border border-line bg-bg p-0 text-fg shadow-2xl max-sm:mb-0 max-sm:w-full max-sm:max-w-none max-sm:rounded-b-none"
    >
      <div className="flex max-h-[inherit] flex-col">
        <header className="flex items-center justify-between gap-4 border-b border-line px-6 py-4">
          <h2 id={titleId} className="text-lg font-semibold tracking-tight">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="-mr-2 inline-flex min-h-11 min-w-11 items-center justify-center rounded-full text-fg-subtle transition hover:bg-surface-2 hover:text-fg"
          >
            <X className="size-[1.25em]" aria-hidden />
          </button>
        </header>
        <div className="overflow-y-auto overscroll-contain px-6 py-5">{children}</div>
        {footer && (
          <footer className="flex justify-end gap-3 border-t border-line px-6 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
            {footer}
          </footer>
        )}
      </div>
    </Dialog>
  );
}

export function Segmented<T extends string>({
  name,
  legend,
  value,
  options,
  onChange,
}: {
  name: string;
  legend: string;
  value: T;
  options: Array<{ value: T; label: string; icon?: ReactNode }>;
  onChange: (value: T) => void;
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium">{legend}</legend>
      <div className="flex gap-1 rounded-full border border-line bg-surface p-1">
        {options.map((o) => (
          <label
            key={o.value}
            className="relative flex min-h-10 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-full px-3 text-sm text-fg-muted transition has-checked:bg-accent has-checked:text-accent-fg has-checked:shadow-sm has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring hover:text-fg has-checked:hover:text-accent-fg"
          >
            <input
              type="radio"
              name={name}
              value={o.value}
              checked={value === o.value}
              onChange={() => onChange(o.value)}
              className="sr-only"
            />
            {o.icon}
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
