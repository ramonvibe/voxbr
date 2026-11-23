"use client";
import Link from "next/link";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/state";
import { StatusBadge } from "@/components/status-badge";
import { dt, duration, REASON, usd } from "@/lib/labels";
import type { Call } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function CallsPage() {
  const { data, error, loading } = useApi<Call[]>("/calls", 5000);
  return (
    <>
      <PageHeader title="Chamadas" />
      {error && <ErrorBox message={error} />}
      {loading ? <Loading /> : data && data.length === 0 ? <Empty>Nenhuma chamada ainda.</Empty> : (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Início</TableHead><TableHead>Status</TableHead><TableHead>Número</TableHead><TableHead>Agente</TableHead>
            <TableHead>Motivo do transbordo</TableHead><TableHead>Duração</TableHead><TableHead className="text-right">Custo</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {data?.map((c) => (
              <TableRow key={c.id}>
                <TableCell><Link className="underline-offset-4 hover:underline" href={`/calls/${c.id}`}>{dt(c.started_at)}</Link></TableCell>
                <TableCell><StatusBadge status={c.status} /></TableCell>
                <TableCell>{c.number_label || c.did}</TableCell>
                <TableCell>{c.agent_name || "—"}</TableCell>
                <TableCell>{c.transfer_reason ? REASON[c.transfer_reason] ?? c.transfer_reason : "—"}</TableCell>
                <TableCell className="tabular-nums">{duration(c.started_at, c.ended_at)}</TableCell>
                <TableCell className="text-right tabular-nums">{usd(c.cost_usd)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </>
  );
}
