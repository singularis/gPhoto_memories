import { useId, type ReactNode } from 'react';
import { Minus, Monitor, Moon, Plus, Sun } from 'lucide-react';
import type { Settings } from '../lib/api';
import type { ThemePref } from '../hooks/useTheme';
import { formatSeconds, stepSeconds } from '../hooks/useSettings';
import { Button, IconButton, Segmented, SheetDialog } from './ui';

export interface SettingsDraft {
  settings: Settings;
  theme: ThemePref;
}

/** Every change previews live; Cancel restores what was saved. */
export function SettingsDialog({
  open,
  draft,
  onChange,
  onSave,
  onCancel,
}: {
  open: boolean;
  draft: SettingsDraft;
  onChange: (draft: SettingsDraft) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const { settings, theme } = draft;
  const set = (patch: Partial<Settings>) => onChange({ theme, settings: { ...settings, ...patch } });

  return (
    <SheetDialog
      open={open}
      onClose={onCancel}
      title="Settings"
      titleId="settings-title"
      footer={
        <>
          <Button onClick={onCancel}>Cancel</Button>
          <Button variant="solid" onClick={onSave}>
            Save
          </Button>
        </>
      }
    >
      <div className="grid gap-6">
        <Segmented
          name="theme"
          legend="Theme"
          value={theme}
          onChange={(t) => onChange({ settings, theme: t })}
          options={[
            { value: 'system', label: 'Auto', icon: <Monitor className="size-[1.1em]" aria-hidden /> },
            { value: 'light', label: 'Light', icon: <Sun className="size-[1.1em]" aria-hidden /> },
            { value: 'dark', label: 'Dark', icon: <Moon className="size-[1.1em]" aria-hidden /> },
          ]}
        />

        <ScaleSlider label="Photo size" value={settings.image_scale} onChange={(v) => set({ image_scale: v })} />
        <ScaleSlider label="Text size" value={settings.font_scale} onChange={(v) => set({ font_scale: v })} />

        <Segmented
          name="order"
          legend="Show years"
          value={settings.year_order}
          onChange={(v) => set({ year_order: v })}
          options={[
            { value: 'newer', label: 'Newest first' },
            { value: 'older', label: 'Oldest first' },
          ]}
        />

        <Row label="Slideshow delay" hint="Time each photo stays on screen">
          <IconButton label="Faster" onClick={() => set({ play_seconds: stepSeconds(settings.play_seconds, -1) })}>
            <Minus className="size-[1.1em]" aria-hidden />
          </IconButton>
          <output className="min-w-16 text-center text-base font-semibold tabular-nums">
            {formatSeconds(settings.play_seconds)}
          </output>
          <IconButton label="Slower" onClick={() => set({ play_seconds: stepSeconds(settings.play_seconds, 1) })}>
            <Plus className="size-[1.1em]" aria-hidden />
          </IconButton>
        </Row>
      </div>
    </SheetDialog>
  );
}

function Row({ label, hint, children }: { label: string; hint: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-fg-subtle">{hint}</p>
      </div>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  );
}

function ScaleSlider({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  const id = useId();
  const clamp = (v: number) => Math.round(Math.min(4, Math.max(0.5, v)) * 10) / 10;
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <label htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
        <output htmlFor={id} className="text-sm text-fg-muted tabular-nums">
          {value.toFixed(1)}×
        </output>
      </div>
      <div className="flex items-center gap-3">
        <IconButton label={`Smaller ${label.toLowerCase()}`} onClick={() => onChange(clamp(value - 0.1))}>
          <Minus className="size-[1.1em]" aria-hidden />
        </IconButton>
        <input
          id={id}
          type="range"
          min={0.5}
          max={4}
          step={0.1}
          value={value}
          onChange={(e) => onChange(clamp(Number(e.target.value)))}
          className="h-2 w-full cursor-pointer"
        />
        <IconButton label={`Larger ${label.toLowerCase()}`} onClick={() => onChange(clamp(value + 0.1))}>
          <Plus className="size-[1.1em]" aria-hidden />
        </IconButton>
      </div>
    </div>
  );
}
