"use client";
import { useState } from "react";
import { FlaskConical } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CallPanel } from "@/components/call-panel";
import { api, errMsg } from "@/lib/api";
import type { LkToken } from "@/lib/types";

/** Botão "Testar no navegador": pede o token e abre o painel de chamada. */
export function TestCallButton({ target, label, size }: {
  target: { number_id: number } | { agent_id: number }; label: string; size?: "sm" | "default";
}) {
  const [conn, setConn] = useState<LkToken>();
  const [busy, setBusy] = useState(false);
  const start = async () => {
    setBusy(true);
    try {
      setConn(await api<LkToken>("/test-call", { method: "POST", json: target }));
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button variant="outline" size={size} onClick={start} disabled={busy}><FlaskConical /> Testar no navegador</Button>
      <Dialog open={!!conn} onOpenChange={(o) => !o && setConn(undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Chamada de teste</DialogTitle>
            <DialogDescription>{label}. Fale normalmente: o agente atende como atenderia no telefone.</DialogDescription>
          </DialogHeader>
          {conn && <CallPanel conn={conn} hangupLabel="Desligar" onHangup={() => setConn(undefined)} onEnded={() => setConn(undefined)} />}
        </DialogContent>
      </Dialog>
    </>
  );
}
