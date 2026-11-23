"use client";
import { useState } from "react";
import { Pencil, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, ErrorBox, Field, Loading, PageHeader } from "@/components/state";
import { api, errMsg } from "@/lib/api";
import { DAY } from "@/lib/labels";
import type { Queue, User } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const DAYS = Object.keys(DAY);
type Ranges = Record<string, [string, string][]>;
type Form = { id?: number; name: string; wait_timeout_s: number; member_ids: number[]; always: boolean; days: Ranges; holidays: string[]; newHoliday: string };
const blank: Form = { name: "", wait_timeout_s: 120, member_ids: [], always: false, days: {}, holidays: [], newHoliday: "" };
const businessDays = (): Ranges => Object.fromEntries(["mon", "tue", "wed", "thu", "fri"].map((d) => [d, [["08:00", "18:00"] as [string, string]]]));

function HoursEditor({ days, onChange }: { days: Ranges; onChange: (d: Ranges) => void }) {
  return (
    <div className="grid gap-2">
      {DAYS.map((d) => {
        const ranges = days[d];
        const setRanges = (r: [string, string][] | undefined) => {
          const next = { ...days };
          if (r) next[d] = r; else delete next[d];
          onChange(next);
        };
        return (
          <div key={d} className="flex flex-wrap items-center gap-2 rounded-lg border p-2">
            <label className="flex w-28 items-center gap-2 text-sm font-medium">
              <input type="checkbox" checked={!!ranges} onChange={(e) => setRanges(e.target.checked ? [["08:00", "18:00"]] : undefined)} />
              {DAY[d]}
            </label>
            {ranges ? (
              <>
                {ranges.map(([a, b], i) => (
                  <span key={i} className="flex items-center gap-1">
                    <Input type="time" className="w-28" value={a} onChange={(e) => setRanges(ranges.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))} />
                    –
                    <Input type="time" className="w-28" value={b} onChange={(e) => setRanges(ranges.map((r, j) => (j === i ? [r[0], e.target.value] : r)))} />
                    {ranges.length > 1 && (
                      <Button type="button" variant="ghost" size="icon-xs" aria-label="Remover faixa" onClick={() => setRanges(ranges.filter((_, j) => j !== i))}><X /></Button>
                    )}
                  </span>
                ))}
                <Button type="button" variant="ghost" size="xs" onClick={() => setRanges([...ranges, ["13:00", "18:00"]])}><Plus /> Faixa</Button>
              </>
            ) : <span className="text-sm text-muted-foreground">Fechada</span>}
          </div>
        );
      })}
    </div>
  );
}

export default function QueuesPage() {
  const queues = useApi<Queue[]>("/queues");
  const users = useApi<User[]>("/users");
  const [form, setForm] = useState<Form>();
  const [error, setError] = useState("");
  const set = (p: Partial<Form>) => setForm((f) => f && { ...f, ...p });

  const open = (q?: Queue) => {
    setError("");
    if (!q) return setForm({ ...blank, days: businessDays() });
    const days = (q.hours?.days ?? {}) as Ranges;
    setForm({ id: q.id, name: q.name, wait_timeout_s: q.wait_timeout_s, member_ids: q.member_ids, always: Object.keys(days).length === 0, days, holidays: q.holidays, newHoliday: "" });
  };
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    if (!form.always && Object.keys(form.days).length === 0) return setError("Marque ao menos um dia aberto ou use “Sempre aberta”.");
    const body = {
      name: form.name, wait_timeout_s: form.wait_timeout_s, member_ids: form.member_ids, holidays: form.holidays,
      hours: { tz: "America/Sao_Paulo", days: form.always ? {} : form.days },
    };
    try {
      await api(form.id ? `/queues/${form.id}` : "/queues", { method: form.id ? "PUT" : "POST", json: body });
      setForm(undefined);
      queues.reload();
      toast.success("Fila salva");
    } catch (err) {
      setError(errMsg(err));
    }
  };
  const remove = async (q: Queue) => {
    if (!confirm(`Excluir a fila ${q.name}?`)) return;
    try {
      await api(`/queues/${q.id}`, { method: "DELETE" });
      queues.reload();
    } catch (err) {
      toast.error(errMsg(err));
    }
  };

  return (
    <>
      <PageHeader title="Filas"><Button onClick={() => open()}><Plus /> Nova fila</Button></PageHeader>
      {queues.error && <ErrorBox message={queues.error} />}
      {queues.loading ? <Loading /> : queues.data && queues.data.length === 0 ? <Empty>Nenhuma fila criada.</Empty> : (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Nome</TableHead><TableHead>Membros</TableHead><TableHead>Espera máx.</TableHead><TableHead>Horário</TableHead>
            <TableHead>Feriados</TableHead><TableHead className="text-right">Ações</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {queues.data?.map((q) => (
              <TableRow key={q.id}>
                <TableCell className="font-medium">{q.name}</TableCell>
                <TableCell>{q.member_ids.length}</TableCell>
                <TableCell>{q.wait_timeout_s}s</TableCell>
                <TableCell>{Object.keys(q.hours?.days ?? {}).length ? `${Object.keys(q.hours.days!).length} dia(s)/semana` : "Sempre aberta"}</TableCell>
                <TableCell>{q.holidays.length}</TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" size="icon-sm" aria-label="Editar" onClick={() => open(q)}><Pencil /></Button>
                    <Button variant="ghost" size="icon-sm" aria-label="Excluir" onClick={() => remove(q)}><Trash2 /></Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={!!form} onOpenChange={(o) => !o && setForm(undefined)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader><DialogTitle>{form?.id ? "Editar fila" : "Nova fila"}</DialogTitle></DialogHeader>
          {form && (
            <form onSubmit={save} className="grid gap-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Nome"><Input required value={form.name} onChange={(e) => set({ name: e.target.value })} /></Field>
                <Field label="Tempo máximo de espera (s)" hint="Entre 15 e 1800.">
                  <Input type="number" min={15} max={1800} required value={form.wait_timeout_s} onChange={(e) => set({ wait_timeout_s: Number(e.target.value) })} />
                </Field>
              </div>
              <div className="grid gap-1.5 text-sm font-medium">
                Membros
                {users.data?.length ? (
                  <div className="grid gap-1 sm:grid-cols-2">
                    {users.data.map((u) => (
                      <label key={u.id} className="flex items-center gap-2 font-normal">
                        <input type="checkbox" checked={form.member_ids.includes(u.id)}
                          onChange={(e) => set({ member_ids: e.target.checked ? [...form.member_ids, u.id] : form.member_ids.filter((i) => i !== u.id) })} />
                        {u.name} <span className="text-xs text-muted-foreground">({u.email})</span>
                      </label>
                    ))}
                  </div>
                ) : <span className="text-xs font-normal text-muted-foreground">Nenhum usuário.</span>}
              </div>
              <div className="grid gap-2">
                <div className="flex items-center justify-between text-sm font-medium">
                  Horário de atendimento (America/Sao_Paulo)
                  <label className="flex items-center gap-2 font-normal">
                    <input type="checkbox" checked={form.always} onChange={(e) => set({ always: e.target.checked })} /> Sempre aberta
                  </label>
                </div>
                {!form.always && <HoursEditor days={form.days} onChange={(days) => set({ days })} />}
              </div>
              <div className="grid gap-2 text-sm font-medium">
                Feriados (fila fechada)
                <div className="flex gap-2">
                  <Input type="date" className="w-44" value={form.newHoliday} onChange={(e) => set({ newHoliday: e.target.value })} />
                  <Button type="button" variant="outline" disabled={!form.newHoliday || form.holidays.includes(form.newHoliday)}
                    onClick={() => set({ holidays: [...form.holidays, form.newHoliday].sort(), newHoliday: "" })}><Plus /> Adicionar</Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {form.holidays.map((h) => (
                    <span key={h} className="flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-xs font-normal">
                      {h.split("-").reverse().join("/")}
                      <button type="button" aria-label="Remover feriado" onClick={() => set({ holidays: form.holidays.filter((x) => x !== h) })}><X className="size-3" /></button>
                    </span>
                  ))}
                  {form.holidays.length === 0 && <span className="text-xs font-normal text-muted-foreground">Nenhum feriado.</span>}
                </div>
              </div>
              {error && <ErrorBox message={error} />}
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setForm(undefined)}>Cancelar</Button>
                <Button type="submit">Salvar</Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
