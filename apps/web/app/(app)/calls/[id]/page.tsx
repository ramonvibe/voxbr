"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBox, Loading, PageHeader } from "@/components/state";
import { StatusBadge } from "@/components/status-badge";
import { Transcript } from "@/components/transcript";
import { dt, duration, REASON, usd } from "@/lib/labels";
import type { Call } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function CallDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: c, error, loading } = useApi<Call>(`/calls/${id}`, (d) => (d && d.status !== "ended" ? 5000 : null));
  return (
    <>
      <Link href="/calls" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Chamadas</Link>
      <PageHeader title={c ? `Chamada #${c.id}` : "Chamada"}>{c && <StatusBadge status={c.status} />}</PageHeader>
      {error && <ErrorBox message={error} />}
      {loading && <Loading />}
      {c && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="grid content-start gap-4 lg:col-span-1">
            <Card>
              <CardHeader><CardTitle>Detalhes</CardTitle></CardHeader>
              <CardContent className="grid gap-2 text-sm">
                {([
                  ["Número", `${c.number_label || "—"} (${c.did})`], ["Origem", c.caller || "—"], ["Agente", c.agent_name || "—"],
                  ["Fila", c.queue_name || "—"], ["Atendente", c.attendant_name || "—"],
                  ["Motivo do transbordo", c.transfer_reason ? REASON[c.transfer_reason] ?? c.transfer_reason : "—"],
                  ["Início", dt(c.started_at)], ["Duração", duration(c.started_at, c.ended_at)], ["Custo total", usd(c.cost_usd)],
                ] as const).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3"><span className="text-muted-foreground">{k}</span><span className="text-right">{v}</span></div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Resumo da IA</CardTitle></CardHeader>
              <CardContent className="whitespace-pre-wrap text-sm">{c.summary || <span className="text-muted-foreground">Sem resumo.</span>}</CardContent>
            </Card>
          </div>
          <div className="grid content-start gap-4 lg:col-span-2">
            <Card>
              <CardHeader><CardTitle>Transcrição</CardTitle></CardHeader>
              <CardContent><Transcript turns={c.transcript} /></CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Custo por provedor</CardTitle></CardHeader>
              <CardContent>
                {c.usage?.length ? (
                  <Table>
                    <TableHeader><TableRow><TableHead>Tipo</TableHead><TableHead>Provedor</TableHead><TableHead>Modelo</TableHead><TableHead className="text-right">Custo</TableHead></TableRow></TableHeader>
                    <TableBody>
                      {c.usage.map((u, i) => (
                        <TableRow key={i}>
                          <TableCell className="uppercase">{u.type}</TableCell><TableCell>{u.provider ?? "—"}</TableCell><TableCell>{u.model ?? "—"}</TableCell>
                          <TableCell className="text-right tabular-nums">{u.cost_usd == null ? <span title="Preço não configurado">sem preço</span> : usd(u.cost_usd)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : <p className="text-sm text-muted-foreground">Sem dados de uso.</p>}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
