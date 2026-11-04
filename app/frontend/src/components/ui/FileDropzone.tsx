import { useRef, useState, type DragEvent } from 'react';
import { cx } from '../../lib/cx';
import { useToast } from './feedback';
import { Icon } from './Icon';

/** Drag-and-drop / click-to-browse box for one PDF, used by both tools so they look and behave the same. */
export function FileDropzone({ onFile, title, hint, maxMb = 30, compact }: {
  onFile: (file: File) => void;
  title: string;
  hint?: string;
  maxMb?: number;
  compact?: boolean;
}) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const pick = (f?: File) => {
    if (input.current) input.current.value = '';
    if (!f) return;
    if (!/\.pdf$/i.test(f.name) && f.type !== 'application/pdf') return toast('Chỉ nhận file PDF', { kind: 'error' });
    if (f.size > maxMb * 1_048_576) return toast(`File lớn hơn ${maxMb} MB`, { kind: 'error' });
    onFile(f);
  };
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]); };

  return (
    <>
      <input ref={input} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => pick(e.target.files?.[0])} />
      <div role="button" tabIndex={0} aria-label="Chọn file PDF" onClick={() => input.current?.click()}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.current?.click(); } }}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}
        className={cx('flex cursor-pointer flex-col items-center gap-2.5 border border-dashed px-5 text-center transition-colors',
          compact ? 'py-8' : 'py-12',
          over ? 'border-primary bg-primary-soft' : 'border-strong bg-surface hover:border-primary hover:bg-primary-soft')}>
        <div className="grid size-11 place-items-center bg-primary-soft text-primary"><Icon name="upload" size={22} /></div>
        <strong className="text-[14px]">{title}</strong>
        <span className="text-xs text-mute">{hint ?? `hoặc bấm để chọn file · tối đa ${maxMb} MB`}</span>
      </div>
    </>
  );
}
