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
import { api, errMsg } from "@/lib/api";
import { ROLE } from "@/lib/labels";
import type { Queue, Role, User } from "@/lib/types";
import { useApi } from "@/lib/use-api";

type Form = { id?: number; email: string; name: string; role: Role; active: boolean; password: string; queue_ids: number[] };
const blank: Form = { email: "", name: "", role: "attendant", active: true, password: "", queue_ids: [] };

export default function UsersPage() {
  const users = useApi<User[]>("/users");
  const queues = useApi<Queue[]>("/queues");
  const [form, setForm] = useState<Form>();
  const [error, setError] = useState("");
  const set = (p: Partial<Form>) => setForm((f) => f && { ...f, ...p });

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setError("");
    const { id, password, ...rest } = form;
    try {
      await api(id ? `/users/${id}` : "/users", { method: id ? "PUT" : "POST", json: { ...rest, ...(password ? { password } : {}) } });
      setForm(undefined);
      users.reload();
      toast.success("Usuário salvo");
    } catch (err) {
      setError(errMsg(err));
    }
  };
  const remove = async (u: User) => {
    if (!confirm(`Excluir ${u.name}?`)) return;
    try {
      await api(`/users/${u.id}`, { method: "DELETE" });
      users.reload();
    } catch (err) {
      toast.error(errMsg(err));
    }
  };
  const qname = (id: number) => queues.data?.find((q) => q.id === id)?.name ?? `#${id}`;

  return (
    <>
      <PageHeader title="Usuários">
        <Button onClick={() => { setError(""); setForm(blank); }}><Plus /> Novo usuário</Button>
      </PageHeader>
      {users.error && <ErrorBox message={users.error} />}
      {users.loading ? <Loading /> : users.data && users.data.length === 0 ? <Empty>Nenhum usuário.</Empty> : (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Nome</TableHead><TableHead>E-mail</TableHead><TableHead>Perfil</TableHead><TableHead>Filas</TableHead>
            <TableHead>Situação</TableHead><TableHead className="text-right">Ações</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {users.data?.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-medium">{u.name}</TableCell>
                <TableCell>{u.email}</TableCell>
                <TableCell>{ROLE[u.role]}</TableCell>
                <TableCell>{u.queue_ids.map(qname).join(", ") || "—"}</TableCell>
                <TableCell><Badge variant={u.active ? "secondary" : "outline"}>{u.active ? "Ativo" : "Inativo"}</Badge></TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" size="icon-sm" aria-label="Editar" onClick={() => { setError(""); setForm({ id: u.id, email: u.email, name: u.name, role: u.role, active: u.active, password: "", queue_ids: u.queue_ids }); }}><Pencil /></Button>
                    <Button variant="ghost" size="icon-sm" aria-label="Excluir" onClick={() => remove(u)}><Trash2 /></Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={!!form} onOpenChange={(o) => !o && setForm(undefined)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{form?.id ? "Editar usuário" : "Novo usuário"}</DialogTitle></DialogHeader>
          {form && (
            <form onSubmit={save} className="grid gap-4">
              <Field label="Nome"><Input required value={form.name} onChange={(e) => set({ name: e.target.value })} /></Field>
              <Field label="E-mail"><Input type="email" required value={form.email} onChange={(e) => set({ email: e.target.value })} /></Field>
              <Field label="Perfil">
                <NativeSelect value={form.role} onChange={(e) => set({ role: e.target.value as Role })}>
                  <option value="attendant">Atendente</option><option value="admin">Administrador</option>
                </NativeSelect>
              </Field>
              <Field label="Senha" hint={form.id ? "Deixe em branco para manter a atual." : "Mínimo de 8 caracteres."}>
                <Input type="password" minLength={8} required={!form.id} autoComplete="new-password" value={form.password} onChange={(e) => set({ password: e.target.value })} />
              </Field>
              <div className="grid gap-1.5 text-sm font-medium">
                Filas
                {queues.data?.length ? queues.data.map((q) => (
                  <label key={q.id} className="flex items-center gap-2 font-normal">
                    <input type="checkbox" checked={form.queue_ids.includes(q.id)}
                      onChange={(e) => set({ queue_ids: e.target.checked ? [...form.queue_ids, q.id] : form.queue_ids.filter((i) => i !== q.id) })} />
                    {q.name}
                  </label>
                )) : <span className="text-xs font-normal text-muted-foreground">Nenhuma fila criada.</span>}
              </div>
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
