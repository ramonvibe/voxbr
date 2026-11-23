"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, ErrorBox, Loading, PageHeader } from "@/components/state";
import { api, errMsg } from "@/lib/api";
import type { Agent, AgentBody, Catalog } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const RULES = `# Regras do agente

## Quem você é
Atendente virtual da empresa. Fale sempre em português do Brasil.

## O que você resolve
- (liste aqui os assuntos que o agente pode atender)

## Quando transferir para um humano
- O cliente pede para falar com uma pessoa.
- O assunto está fora da lista acima.
`;

export default function AgentsPage() {
  const agents = useApi<Agent[]>("/agents");
  const catalog = useApi<Catalog>("/catalog");
  const router = useRouter();

  const create = async () => {
    // Novo agente herda os modelos do primeiro existente; sem nenhum, usa o primeiro item do catálogo.
    const base = agents.data?.[0];
    const first = (k: "stt" | "llm" | "tts" | "embedding") => {
      const [vendor, models] = Object.entries(catalog.data?.providers[k] ?? {})[0] ?? ["", []];
      return { vendor, model: models[0] ?? "", options: {} };
    };
    const body: AgentBody = {
      name: "Novo agente", rules_md: RULES, greeting: "Olá! Como posso ajudar?",
      recording_notice: "Esta ligação pode ser gravada para fins de qualidade e segurança.", language: "pt", voice_mode: "pipeline", realtime: base?.realtime ?? [],
      stt: base?.stt ?? [first("stt")], llm: base?.llm ?? [first("llm")], tts: base?.tts ?? [first("tts")],
      embedding: base?.embedding ?? first("embedding"), rag_min_score: base?.rag_min_score ?? 0.35,
    };
    try {
      const a = await api<Agent>("/agents", { method: "POST", json: body });
      router.push(`/agents/${a.id}`);
    } catch (e) {
      toast.error(errMsg(e));
    }
  };
  const remove = async (a: Agent) => {
    if (!confirm(`Excluir o agente ${a.name}?`)) return;
    try {
      await api(`/agents/${a.id}`, { method: "DELETE" });
      agents.reload();
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <>
      <PageHeader title="Agentes IA"><Button onClick={create} disabled={!catalog.data}><Plus /> Novo agente</Button></PageHeader>
      {agents.error && <ErrorBox message={agents.error} />}
      {agents.loading ? <Loading /> : agents.data && agents.data.length === 0 ? <Empty>Nenhum agente criado.</Empty> : (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Nome</TableHead><TableHead>LLM principal</TableHead><TableHead>Voz principal</TableHead><TableHead>Documentos</TableHead><TableHead className="text-right">Ações</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {agents.data?.map((a) => (
              <TableRow key={a.id}>
                <TableCell><Link className="font-medium underline-offset-4 hover:underline" href={`/agents/${a.id}`}>{a.name}</Link></TableCell>
                <TableCell>{a.llm[0]?.vendor} / {a.llm[0]?.model}</TableCell>
                <TableCell>{a.tts[0]?.vendor} / {a.tts[0]?.model}</TableCell>
                <TableCell>{a.document_count}</TableCell>
                <TableCell className="text-right">
                  <Button variant="ghost" size="icon-sm" aria-label="Excluir" onClick={() => remove(a)}><Trash2 /></Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </>
  );
}
