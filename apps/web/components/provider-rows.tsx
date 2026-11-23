"use client";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/native-select";
import type { Provider } from "@/lib/types";

/** Linha editável: `options` fica como texto JSON até salvar. */
export interface Row { vendor: string; model: string; options: string }
export const toRow = (p: Provider): Row => ({ vendor: p.vendor, model: p.model, options: Object.keys(p.options ?? {}).length ? JSON.stringify(p.options) : "" });
export function fromRow(r: Row, label: string): Provider {
  if (!r.vendor || !r.model.trim()) throw new Error(`${label}: preencha provedor e modelo`);
  let options = {};
  if (r.options.trim()) {
    try {
      options = JSON.parse(r.options);
      if (typeof options !== "object" || Array.isArray(options) || !options) throw 0;
    } catch {
      throw new Error(`${label}: opções devem ser um objeto JSON válido`);
    }
  }
  return { vendor: r.vendor, model: r.model.trim(), options };
}

function RowEditor({ id, row, catalog, onChange, children }: {
  id: string; row: Row; catalog: Record<string, string[]>; onChange: (r: Row) => void; children?: React.ReactNode;
}) {
  const vendors = Object.keys(catalog);
  if (row.vendor && !vendors.includes(row.vendor)) vendors.push(row.vendor);
  return (
    <div className="grid grid-cols-[9rem_1fr_1fr_auto] items-center gap-2">
      <NativeSelect aria-label="Provedor" value={row.vendor} onChange={(e) => onChange({ ...row, vendor: e.target.value })}>
        <option value="">Provedor…</option>
        {vendors.map((v) => <option key={v} value={v}>{v}</option>)}
      </NativeSelect>
      <Input aria-label="Modelo" placeholder="Modelo" list={`${id}-models`} value={row.model} onChange={(e) => onChange({ ...row, model: e.target.value })} />
      <datalist id={`${id}-models`}>{(catalog[row.vendor] ?? []).map((m) => <option key={m} value={m} />)}</datalist>
      <Input aria-label="Opções (JSON)" placeholder='Opções JSON, ex.: {"voice":"x"}' className="font-mono text-xs" value={row.options} onChange={(e) => onChange({ ...row, options: e.target.value })} />
      <div className="flex">{children}</div>
    </div>
  );
}

export function ProviderList({ id, rows, catalog, onChange, minRows = 1 }: {
  id: string; rows: Row[]; minRows?: number; catalog: Record<string, string[]>; onChange: (r: Row[]) => void;
}) {
  const move = (i: number, d: number) => {
    const next = [...rows];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    onChange(next);
  };
  return (
    <div className="grid gap-2">
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="w-6 text-center text-xs text-muted-foreground">{i === 0 ? "1º" : `${i + 1}º`}</span>
          <div className="flex-1">
            <RowEditor id={`${id}-${i}`} row={r} catalog={catalog} onChange={(nr) => onChange(rows.map((x, j) => (j === i ? nr : x)))}>
              <Button type="button" variant="ghost" size="icon-sm" aria-label="Subir" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp /></Button>
              <Button type="button" variant="ghost" size="icon-sm" aria-label="Descer" disabled={i === rows.length - 1} onClick={() => move(i, 1)}><ArrowDown /></Button>
              <Button type="button" variant="ghost" size="icon-sm" aria-label="Remover" disabled={rows.length <= minRows} onClick={() => onChange(rows.filter((_, j) => j !== i))}><Trash2 /></Button>
            </RowEditor>
          </div>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => onChange([...rows, { vendor: Object.keys(catalog)[0] ?? "", model: "", options: "" }])}>
        <Plus /> {minRows === 0 && rows.length === 0 ? "Adicionar modelo" : "Adicionar fallback"}
      </Button>
    </div>
  );
}

export function SingleProvider({ id, row, catalog, onChange }: { id: string; row: Row; catalog: Record<string, string[]>; onChange: (r: Row) => void }) {
  return <RowEditor id={id} row={row} catalog={catalog} onChange={onChange} />;
}
