"use client";
import { useRef, useState } from "react";
import { Link2, RefreshCw, Search, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, ErrorBox, Loading } from "@/components/state";
import { api, errMsg } from "@/lib/api";
import { dt } from "@/lib/labels";
import type { Doc, SearchHit } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const STATUS = { processing: "Processando", ready: "Pronto", error: "Erro" } as const;

export function KnowledgeTab({ agentId }: { agentId: number }) {
  const { data, error, loading, reload } = useApi<Doc[]>(`/agents/${agentId}/documents`, (d) => (d?.some((x) => x.status === "processing") ? 2000 : null));
  const fileRef = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>();
  const [searching, setSearching] = useState(false);

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true);
    try {
      await fn();
      if (ok) toast.success(ok);
      reload();
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  const upload = (f: File) => run(() => { const fd = new FormData(); fd.append("file", f); return api(`/agents/${agentId}/documents`, { method: "POST", body: fd }); }, "Arquivo enviado");
  const addUrl = () => run(async () => { await api(`/agents/${agentId}/documents/url`, { method: "POST", json: { url } }); setUrl(""); }, "Endereço adicionado");
  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    setSearching(true);
    try {
      setHits(await api<SearchHit[]>(`/agents/${agentId}/search`, { method: "POST", json: { query } }));
    } catch (err) {
      toast.error(errMsg(err));
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader><CardTitle>Documentos</CardTitle></CardHeader>
        <CardContent className="grid gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <input ref={fileRef} type="file" hidden accept=".pdf,.docx,.txt,.md" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
            <Button variant="outline" disabled={busy} onClick={() => fileRef.current?.click()}><Upload /> Enviar arquivo</Button>
            <span className="text-xs text-muted-foreground">PDF, DOCX, TXT ou MD, até 20 MB.</span>
            <div className="ml-auto flex gap-2">
              <Input className="w-72" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
              <Button variant="outline" disabled={busy || !url} onClick={addUrl}><Link2 /> Adicionar endereço</Button>
            </div>
            <Button variant="outline" disabled={busy} onClick={() => run(() => api(`/agents/${agentId}/reindex`, { method: "POST" }), "Reindexação iniciada")}><RefreshCw /> Reindexar</Button>
          </div>
          {error && <ErrorBox message={error} />}
          {loading ? <Loading /> : data && data.length === 0 ? <Empty>Nenhum documento. Envie um arquivo ou adicione um endereço.</Empty> : (
            <Table>
              <TableHeader><TableRow><TableHead>Nome</TableHead><TableHead>Status</TableHead><TableHead>Trechos</TableHead><TableHead>Adicionado</TableHead><TableHead /></TableRow></TableHeader>
              <TableBody>
                {data?.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell><div className="font-medium">{d.name}</div>{d.error && <div className="text-xs text-destructive">{d.error}</div>}</TableCell>
                    <TableCell><Badge variant={d.status === "error" ? "destructive" : "secondary"}>{STATUS[d.status] ?? d.status}</Badge></TableCell>
                    <TableCell>{d.chunk_count}</TableCell>
                    <TableCell>{dt(d.created_at)}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon-sm" aria-label="Excluir" onClick={() => confirm(`Excluir ${d.name}?`) && run(() => api(`/documents/${d.id}`, { method: "DELETE" }))}><Trash2 /></Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Testar busca</CardTitle></CardHeader>
        <CardContent className="grid gap-3">
          <form onSubmit={search} className="flex gap-2">
            <Input placeholder="Pergunta de um cliente, ex.: qual o horário de funcionamento?" value={query} onChange={(e) => setQuery(e.target.value)} />
            <Button type="submit" disabled={searching || !query.trim()}><Search /> Buscar</Button>
          </form>
          {hits && (hits.length === 0 ? <p className="text-sm text-muted-foreground">Nenhum trecho encontrado.</p> : hits.map((h, i) => (
            <div key={i} className="rounded-lg border p-3 text-sm">
              <div className="mb-1 flex items-center gap-2">
                <Badge variant={h.relevant ? "secondary" : "outline"} className={h.relevant ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" : ""}>{h.relevant ? "Relevante" : "Abaixo do mínimo"}</Badge>
                <span className="tabular-nums text-xs text-muted-foreground">score {h.score.toFixed(3)}</span>
              </div>
              <p className="whitespace-pre-wrap">{h.text}</p>
            </div>
          )))}
        </CardContent>
      </Card>
    </div>
  );
}
