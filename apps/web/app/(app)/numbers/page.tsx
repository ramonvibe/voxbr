"use client";
import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { NativeSelect } from "@/components/native-select";
import { Empty, ErrorBox, Field, Loading, PageHeader } from "@/components/state";
import { TestCallButton } from "@/components/test-call";
import { api, errMsg } from "@/lib/api";
import { MODE } from "@/lib/labels";
import type { Agent, NumberRow, Queue } from "@/lib/types";
import { useApi } from "@/lib/use-api";

type Form = { id?: number; did: string; label: string; mode: "ai" | "human_direct"; agent_id: string; queue_id: string; retention_days: number; active: boolean };
const blank: Form = { did: "", label: "", mode: "ai", agent_id: "", queue_id: "", retention_days: 90, active: true };

export default function NumbersPage() {
  const nums = useApi<NumberRow[]>("/numbers");
  const agents = useApi<Agent[]>("/agents");
  const queues = useApi<Queue[]>("/queues");
  const [form, setForm] = useState<Form>();
  const [error, setError] = useState("");

  const set = (p: Partial<Form>) => setForm((f) => f && { ...f, ...p });
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setError("");
    const body = {
      did: form.did, label: form.label, mode: form.mode, retention_days: form.retention_days, active: form.active,
      agent_id: form.mode === "ai" && form.agent_id ? Number(form.agent_id) : null,
      queue_id: form.queue_id ? Number(form.queue_id) : null,
    };
    try {
      await api(form.id ? `/numbers/${form.id}` : "/numbers", { method: form.id ? "PUT" : "POST", json: body });
      setForm(undefined);
      nums.reload();
      toast.success("Número salvo");
    } catch (err) {
      setError(errMsg(err));
    }
  };
  const remove = async (n: NumberRow) => {
    if (!confirm(`Excluir o número ${n.did}?`)) return;
    try {
      await api(`/numbers/${n.id}`, { method: "DELETE" });
      nums.reload();
    } catch (err) {
      toast.error(errMsg(err));
    }
  };

  return (
    <>
      <PageHeader title="Números">
        <Button onClick={() => { setError(""); setForm({ ...blank, agent_id: String(agents.data?.[0]?.id ?? "") }); }}><Plus /> Novo número</Button>
      </PageHeader>
      {nums.error && <ErrorBox message={nums.error} />}
      {nums.loading ? <Loading /> : nums.data && nums.data.length === 0 ? <Empty>Nenhum número cadastrado.</Empty> : (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Número</TableHead><TableHead>Nome</TableHead><TableHead>Modo</TableHead><TableHead>Agente</TableHead>
            <TableHead>Fila</TableHead><TableHead>Situação</TableHead><TableHead className="text-right">Ações</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {nums.data?.map((n) => (
              <TableRow key={n.id}>
                <TableCell className="font-mono">{n.did}</TableCell>
                <TableCell>{n.label || "—"}</TableCell>
                <TableCell>{MODE[n.mode]}</TableCell>
                <TableCell>{n.agent_name ?? "—"}</TableCell>
                <TableCell>{n.queue_name ?? "—"}</TableCell>
                <TableCell><Badge variant={n.active ? "secondary" : "outline"}>{n.active ? "Ativo" : "Inativo"}</Badge></TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <TestCallButton size="sm" target={{ number_id: n.id }} label={`Número ${n.did}`} />
                    <Button variant="ghost" size="icon-sm" aria-label="Editar" onClick={() => { setError(""); setForm({ id: n.id, did: n.did, label: n.label, mode: n.mode, agent_id: String(n.agent_id ?? ""), queue_id: String(n.queue_id ?? ""), retention_days: n.retention_days, active: n.active }); }}><Pencil /></Button>
                    <Button variant="ghost" size="icon-sm" aria-label="Excluir" onClick={() => remove(n)}><Trash2 /></Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={!!form} onOpenChange={(o) => !o && setForm(undefined)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{form?.id ? "Editar número" : "Novo número"}</DialogTitle></DialogHeader>
          {form && (
            <form onSubmit={save} className="grid gap-4">
              <Field label="Número (E.164)" hint="Ex.: +5531999990000"><Input required value={form.did} onChange={(e) => set({ did: e.target.value })} placeholder="+5531999990000" /></Field>
              <Field label="Nome"><Input value={form.label} onChange={(e) => set({ label: e.target.value })} placeholder="Ex.: Suporte" /></Field>
              <Field label="Modo">
                <NativeSelect value={form.mode} onChange={(e) => set({ mode: e.target.value as Form["mode"] })}>
                  <option value="ai">IA atende (pode transferir para a fila)</option>
                  <option value="human_direct">Direto para a fila</option>
                </NativeSelect>
              </Field>
              {form.mode === "ai" && (
                <Field label="Agente IA">
                  <NativeSelect required value={form.agent_id} onChange={(e) => set({ agent_id: e.target.value })}>
                    <option value="">Selecione…</option>
                    {agents.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </NativeSelect>
                </Field>
              )}
              <Field label={form.mode === "ai" ? "Fila de transferência (opcional)" : "Fila"}>
                <NativeSelect required={form.mode === "human_direct"} value={form.queue_id} onChange={(e) => set({ queue_id: e.target.value })}>
                  <option value="">{form.mode === "ai" ? "Sem transferência" : "Selecione…"}</option>
                  {queues.data?.map((q) => <option key={q.id} value={q.id}>{q.name}</option>)}
                </NativeSelect>
              </Field>
              <Field label="Retenção das gravações/transcrições (dias)">
                <Input type="number" min={1} max={3650} value={form.retention_days} onChange={(e) => set({ retention_days: Number(e.target.value) })} />
              </Field>
              <label className="flex items-center gap-2 text-sm font-medium"><Switch checked={form.active} onCheckedChange={(v) => set({ active: v })} /> Ativo</label>
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
