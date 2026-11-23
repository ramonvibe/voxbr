"use client";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Headset, Phone } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CallPanel } from "@/components/call-panel";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/state";
import { Transcript } from "@/components/transcript";
import { api, errMsg } from "@/lib/api";
import { duration, REASON } from "@/lib/labels";
import type { Call, LkToken } from "@/lib/types";
import { useApi } from "@/lib/use-api";

function Details({ c }: { c: Call }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <p className="whitespace-pre-wrap text-sm">{c.summary || <span className="text-muted-foreground">Sem resumo da IA.</span>}</p>
      <Button variant="ghost" size="sm" className="w-fit" onClick={() => setOpen(!open)}>
        {open ? <ChevronUp /> : <ChevronDown />} {open ? "Ocultar transcrição" : "Ver transcrição"}
      </Button>
      {open && <div className="max-h-72 overflow-y-auto rounded-lg border p-3"><Transcript turns={c.transcript} /></div>}
    </>
  );
}

export default function ConsolePage() {
  const { data, error, loading, reload } = useApi<{ waiting: Call[]; active: Call[] }>("/console", 2000);
  const [conns, setConns] = useState<Record<number, LkToken>>({});
  const [busy, setBusy] = useState<number>();
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  // Após recarregar a página, reconecta o áudio das chamadas ativas (uma tentativa por chamada).
  const tried = useRef(new Set<number>());
  useEffect(() => {
    for (const c of data?.active ?? []) {
      if (conns[c.id] || tried.current.has(c.id)) continue;
      tried.current.add(c.id);
      api<LkToken>(`/console/calls/${c.id}/accept`, { method: "POST" })
        .then((conn) => setConns((m) => ({ ...m, [c.id]: conn })))
        .catch(() => {});
    }
  }, [data, conns]);

  const accept = async (c: Call) => {
    setBusy(c.id);
    try {
      const conn = await api<LkToken>(`/console/calls/${c.id}/accept`, { method: "POST" });
      setConns((m) => ({ ...m, [c.id]: conn }));
      await reload();
    } catch (e) {
      toast.error(errMsg(e));
      reload();
    } finally {
      setBusy(undefined);
    }
  };
  // Queda da conexão deste navegador (ou saída da página): só esquece o áudio; o atendente pode reconectar.
  const dropConn = (id: number) => setConns((m) => Object.fromEntries(Object.entries(m).filter(([k]) => Number(k) !== id)));
  const hangup = async (c: Call) => {
    try {
      await api(`/console/calls/${c.id}/hangup`, { method: "POST" });
    } catch (e) {
      toast.error(errMsg(e));
    }
    dropConn(c.id);
    reload();
  };

  return (
    <>
      <PageHeader title="Console" />
      {error && <ErrorBox message={error} />}
      {loading ? <Loading /> : data && (
        <div className="grid gap-8">
          <section className="grid gap-3">
            <h2 className="text-lg font-medium">Em atendimento</h2>
            {data.active.length === 0 ? <Empty>Você não está em nenhuma chamada.</Empty> : data.active.map((c) => (
              <Card key={c.id} className="border-emerald-500/50">
                <CardHeader><CardTitle className="flex items-center gap-2"><Headset className="size-4" /> {c.number_label || c.did} · {c.queue_name}</CardTitle></CardHeader>
                <CardContent className="grid gap-3">
                  <div className="text-sm text-muted-foreground">Origem: {c.caller || "oculta"} · Duração {duration(c.started_at, null)}</div>
                  <Details c={c} />
                  {conns[c.id] ? (
                    <CallPanel conn={conns[c.id]} hangupLabel="Encerrar" onHangup={() => hangup(c)}
                      onEnded={() => dropConn(c.id)} onOthersLeft={() => hangup(c)} />
                  ) : (
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="text-sm text-amber-600 dark:text-amber-400">Áudio não conectado neste navegador.</span>
                      <Button disabled={busy === c.id} onClick={() => accept(c)}><Phone /> Reconectar áudio</Button>
                      <Button variant="destructive" onClick={() => hangup(c)}>Encerrar</Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </section>

          <section className="grid gap-3">
            <h2 className="text-lg font-medium">Aguardando atendente ({data.waiting.length})</h2>
            {data.waiting.length === 0 ? <Empty>Nenhuma chamada aguardando.</Empty> : data.waiting.map((c) => (
              <Card key={c.id} className="border-amber-500/50">
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center justify-between gap-2">
                    <span>{c.queue_name || "Sem fila"} · {c.number_label || c.did}</span>
                    <span className="flex items-center gap-2 text-sm font-normal">
                      {c.transfer_reason && <Badge variant="secondary">{REASON[c.transfer_reason] ?? c.transfer_reason}</Badge>}
                      <span className="tabular-nums">Espera {duration(c.waiting_since ?? c.started_at, null)}</span>
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3">
                  <Details c={c} />
                  <Button className="w-fit" disabled={busy === c.id} onClick={() => accept(c)}><Phone /> Atender</Button>
                </CardContent>
              </Card>
            ))}
          </section>
        </div>
      )}
    </>
  );
}
