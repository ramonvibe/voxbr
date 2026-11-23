"use client";
import { Check, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/state";
import { api, errMsg } from "@/lib/api";
import { dt } from "@/lib/labels";
import type { Msg } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function MessagesPage() {
  const { data, error, loading, reload } = useApi<Msg[]>("/messages", 10000);
  const toggle = async (m: Msg) => {
    try {
      await api(`/messages/${m.id}`, { method: "PATCH", json: { done: !m.done } });
      reload();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  return (
    <>
      <PageHeader title="Recados" />
      {error && <ErrorBox message={error} />}
      {loading ? <Loading /> : data && data.length === 0 ? <Empty>Nenhum recado.</Empty> : (
        <div className="grid gap-3">
          {data?.map((m) => (
            <Card key={m.id} className={m.done ? "opacity-60" : ""}>
              <CardContent className="flex flex-wrap items-start justify-between gap-3">
                <div className="grid gap-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{m.name || "Sem nome"}</span>
                    <span className="font-mono text-sm">{m.callback_number}</span>
                    {m.queue_name && <Badge variant="outline">{m.queue_name}</Badge>}
                    {m.done && <Badge variant="secondary">Resolvido</Badge>}
                  </div>
                  <p className="whitespace-pre-wrap text-sm">{m.message}</p>
                  <span className="text-xs text-muted-foreground">{dt(m.created_at)}</span>
                </div>
                <Button variant="outline" size="sm" onClick={() => toggle(m)}>
                  {m.done ? <><Undo2 /> Reabrir</> : <><Check /> Marcar como resolvido</>}
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
