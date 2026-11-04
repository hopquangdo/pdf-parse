import { forwardRef, useMemo, type ReactElement } from 'react';
import DataGrid, { SelectColumn, textEditor, type Column, type DataGridHandle, type RenderEditCellProps } from 'react-data-grid';
import 'react-data-grid/lib/styles.css';
import type { Issue, MemberType, Row } from '../../api/types';
import { Badge } from '../../components/ui/primitives';
import { fmt, type Computed, type Totals } from '../../lib/formulas';
import { MEMBER_TYPES, invalidFields, parseCell, sameRow, type Field, type SheetRow } from '../../lib/sheet';

const NUMERIC: Field[] = ['w', 't', 'len', 'qty'];
const FIELDS: Field[] = ['section', 'mark', 'type', 'w', 't', 'len', 'qty'];

/** The bottom "Total" row of the template (SUBTOTAL of mass and paint area). */
interface TotalRow { id: '__total' }
const TOTAL_ROW: TotalRow = { id: '__total' };

function TypeEditor({ row, onRowChange, onClose }: RenderEditCellProps<SheetRow, TotalRow>) {
  return (
    <select className="editor" autoFocus value={row.type} aria-label="Loại"
      onChange={(e) => onRowChange({ ...row, type: e.target.value as MemberType }, true)}
      onBlur={() => onClose(true, false)}>
      {MEMBER_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
    </select>
  );
}

interface Props {
  rows: SheetRow[];
  rowNumbers: Map<string, number>;
  byMark: Map<string, Issue[]>;
  baseline: Map<string, Row>;
  calc: Map<string, Computed>;
  totals: Totals;
  /** Template columns D-G (type, width, thickness, length) are hidden in Excel; show them to edit the numbers. */
  showInputs: boolean;
  isFlagged: (row: SheetRow) => boolean;
  selected: ReadonlySet<string>;
  flashId: string | null;
  onSelectedChange: (s: Set<string>) => void;
  onCommit: (updated: SheetRow[]) => void;
  onActiveRow: (rowIdx: number) => void;
}

type Col = Column<SheetRow, TotalRow>;

/**
 * Spreadsheet-style grid mirroring the template: A-I are inputs (and the Spec formula), J-N are the template's
 * formulas evaluated live. Cell cursor, F2/Enter edit, Tab and arrow navigation, copy & paste, resizable columns.
 */
export const SheetGrid = forwardRef<DataGridHandle, Props>(function SheetGrid(
  { rows, rowNumbers, byMark, baseline, calc, totals, showInputs, isFlagged, selected, flashId, onSelectedChange, onCommit, onActiveRow }, ref,
) {
  const columns = useMemo<Col[]>(() => {
    const cls = (field: Field) => (row: SheetRow) =>
      [NUMERIC.includes(field) && 'cell-num', invalidFields(row).has(field) && 'cell-invalid'].filter(Boolean).join(' ') || undefined;
    const input = (key: Field, name: string | ReactElement, width: string): Col => ({
      key, name, width, resizable: true, renderEditCell: textEditor, cellClass: cls(key),
    });
    /** Header cell: the title stays on one line, the unit sits on a second line beneath it. */
    const head = (label: string, hint: string, unit?: string) => (
      <span title={hint} className="hd"><span className="hd-t">{label}</span>{unit && <span className="hd-u">{unit}</span>}</span>
    );

    /** Read-only formula column: right-aligned number, red #N/A when a lookup failed. */
    const formula = (key: string, label: string, unit: string, hint: string, digits: number, pick: (c: Computed) => number | null,
      total?: (t: Totals) => number): Col => ({
      key, name: head(label, hint, unit), width: 'minmax(104px, 1fr)', resizable: true, cellClass: 'cell-calc cell-num',
      renderCell: ({ row }) => {
        const c = calc.get(row.id);
        if (!c) return null;
        if (c.error && (key === '__K' || key === '__M')) return <span className="cell-na" title={c.error}>#N/A</span>;
        return fmt(pick(c), digits);
      },
      renderSummaryCell: total
        ? () => <strong title={totals.errors ? `${totals.errors} dòng không tính được` : undefined}>{fmt(total(totals), digits)}{totals.errors ? '*' : ''}</strong>
        : undefined,
      summaryCellClass: 'cell-num',
    });

    return [
      { key: '__rn', name: 'STT', width: 46, frozen: true, resizable: false, cellClass: 'rn', headerCellClass: 'rn-head',
        renderCell: ({ row }) => rowNumbers.get(row.id) ?? '', renderSummaryCell: () => 'Σ', summaryCellClass: 'rn' },
      { ...SelectColumn, width: 34, resizable: false },
      { ...input('section', 'Đoạn cột', 'minmax(110px, 1.2fr)'), renderSummaryCell: () => <strong>Tổng cộng</strong> },
      input('mark', 'Mã Thanh', 'minmax(92px, 1fr)'),
      ...(showInputs ? [
        { key: 'type', name: 'Loại thép hình', width: 'minmax(96px, 1fr)', resizable: true, renderEditCell: TypeEditor, cellClass: cls('type'),
          renderCell: ({ row }: { row: SheetRow }) => MEMBER_TYPES.find((t) => t.value === row.type)?.label ?? row.type } as Col,
        input('w', head('Rộng (Đ.kính)', 'Rộng hoặc đường kính (mm)', '(mm)'), 'minmax(88px, .8fr)'),
        input('t', head('Dày (Bộ)', 'Dày (mm), hoặc Bộ với bu lông', '(mm)'), 'minmax(80px, .8fr)'),
        input('len', head('Dài', 'Chiều dài (mm)', '(mm)'), 'minmax(76px, .9fr)'),
      ] : []),
      { key: '__spec', name: head('Quy cách - kích thước', 'Quy cách (công thức)'), width: 'minmax(170px, 1.6fr)', resizable: true, cellClass: 'cell-calc',
        renderCell: ({ row }) => calc.get(row.id)?.spec ?? '' },
      input('qty', head('Số lượng', 'Số lượng mỗi cấu kiện', '(ck)'), 'minmax(84px, .6fr)'),
      formula('__J', 'C.dài; d.tích', '(m;m²)', 'Chiều dài (m) hoặc diện tích (m²) của một chi tiết', 3, (c) => c.unit),
      formula('__K', 'Đ.trọng', '(kg/m; kg/m²)', 'Đơn trọng (kg/m, kg/m² hoặc kg mỗi bu lông)', 3, (c) => c.unitWeight),
      formula('__L', 'Tổng C.dài; d.tích', '(m;m²)', 'Tổng chiều dài (m) hoặc diện tích (m²)', 3, (c) => c.totalLen),
      formula('__M', 'Khối lượng', '(kg)', 'Khối lượng (kg)', 2, (c) => c.mass, (t) => t.mass),
      formula('__N', 'Diện tích sơn', '(m²)', 'Diện tích sơn (m²)', 3, (c) => c.paint, (t) => t.paint),
      { key: '__status', name: 'Trạng thái', width: 'minmax(76px, .9fr)', resizable: true, cellClass: 'cell-status',
        renderCell: ({ row }) => {
          const msgs = [...(byMark.get(row.mark ?? '')?.map((i) => i.message) ?? []), calc.get(row.id)?.error].filter(Boolean).join('\n');
          if (isFlagged(row)) return <Badge tone="warn" title={msgs || 'Hãy sửa các ô được tô màu'}>Cần soát</Badge>;
          return sameRow(row, baseline.get(row.id)) ? null : <Badge tone="muted">Đã sửa</Badge>;
        } },
    ];
  }, [rowNumbers, byMark, baseline, calc, totals, showInputs, isFlagged]);

  return (
    <DataGrid<SheetRow, TotalRow, string>
      ref={ref}
      className="excel"
      columns={columns}
      rows={rows}
      bottomSummaryRows={[TOTAL_ROW]}
      rowKeyGetter={(r) => r.id}
      rowHeight={32}
      headerRowHeight={52}
      summaryRowHeight={34}
      selectedRows={selected}
      onSelectedRowsChange={onSelectedChange}
      defaultColumnOptions={{ resizable: true }}
      rowClass={(r) => [isFlagged(r) && 'row-flag', r.id === flashId && 'row-flash'].filter(Boolean).join(' ') || undefined}
      onSelectedCellChange={({ rowIdx }) => onActiveRow(rowIdx)}
      onRowsChange={(updated, { indexes, column }) => {
        const key = column.key as Field;
        onCommit(indexes.map((i) => {
          const row = updated[i];
          return NUMERIC.includes(key) && typeof row[key] === 'string' ? { ...row, [key]: parseCell(key, row[key] as string) } : row;
        }));
      }}
      onPaste={({ sourceColumnKey, sourceRow, targetColumnKey, targetRow }) => {
        const src = sourceColumnKey as Field, dst = targetColumnKey as Field;
        if (!FIELDS.includes(src) || !FIELDS.includes(dst)) return targetRow;
        const value = sourceRow[src];
        if (dst === 'type') return MEMBER_TYPES.some((t) => t.value === value) ? { ...targetRow, type: value as MemberType } : targetRow;
        return { ...targetRow, [dst]: typeof value === 'string' && NUMERIC.includes(dst) ? parseCell(dst, value) : value };
      }}
    />
  );
});
