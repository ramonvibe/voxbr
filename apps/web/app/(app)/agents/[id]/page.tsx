"use client";
import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Save, TriangleAlert } from "lucide-react";
import Markdown from "react-markdown";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { NativeSelect } from "@/components/native-select";
import { Textarea } from "@/components/ui/textarea";
import { ErrorBox, Field, Loading, PageHeader } from "@/components/state";
import { KnowledgeTab } from "@/components/knowledge-tab";
import { fromRow, ProviderList, SingleProvider, toRow, type Row } from "@/components/provider-rows";
import { TestCallButton } from "@/components/test-call";
import { api, errMsg } from "@/lib/api";
import { KIND } from "@/lib/labels";
import type { Agent, AgentBody, Catalog } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface Form {
  name: string; rules_md: string; greeting: string; recording_notice: string; rag_min_score: number;
  voice_mode: "pipeline" | "realtime"; realtime: Row[];
  stt: Row[]; llm: Row[]; tts: Row[]; embedding: Row;
}
const KINDS = ["stt", "llm", "tts"] as const;

function toForm(a: Agent): Form {
  return {
    name: a.name, rules_md: a.rules_md, greeting: a.greeting, recording_notice: a.recording_notice, rag_min_score: a.rag_min_score,
    voice_mode: a.voice_mode ?? "pipeline", realtime: (a.realtime ?? []).map(toRow), stt: a.stt.map(toRow), llm: a.llm.map(toRow), tts: a.tts.map(toRow), embedding: toRow(a.embedding),
  };
}

export default function AgentPage() {
  const { id } = useParams<{ id: string }>();
  const agent = useApi<Agent>(`/agents/${id}`);
  const catalog = useApi<Catalog>("/catalog");
  const [edited, setEdited] = useState<Form>();
  const form = edited ?? (agent.data ? toForm(agent.data) : undefined);
  const [saving, setSaving] = useState(false);
  const [stale, setStale] = useState(0);
  const [saveError, setSaveError] = useState("");
  const set = (p: Partial<Form>) => setEdited((f) => ({ ...(f ?? toForm(agent.data!)), ...p }));

  const save = async () => {
    if (!form || !agent.data) return;
    setSaveError("");
    let body: AgentBody;
    try {
      body = {
        name: form.name, rules_md: form.rules_md, greeting: form.greeting, recording_notice: form.recording_notice,
        language: agent.data.language, voice_mode: form.voice_mode,
        realtime: form.realtime.map((r, i) => fromRow(r, `Realtime ${i + 1}`)), rag_min_score: form.rag_min_score,
        stt: form.stt.map((r, i) => fromRow(r, `STT ${i + 1}`)), llm: form.llm.map((r, i) => fromRow(r, `LLM ${i + 1}`)),
        tts: form.tts.map((r, i) => fromRow(r, `TTS ${i + 1}`)), embedding: fromRow(form.embedding, "Embedding"),
      };
    } catch (e) {
      return setSaveError(errMsg(e));
    }
    setSaving(true);
    try {
      const out = await api<Agent>(`/agents/${id}`, { method: "PUT", json: body });
      setStale(out.stale_chunks ?? 0);
      toast.success("Agente salvo");
    } catch (e) {
      setSaveError(errMsg(e));
    } finally {
      setSaving(false);
    }
  };
  const reindex = async () => {
    try {
      await api(`/agents/${id}/reindex`, { method: "POST" });
      setStale(0);
      toast.success("Reindexação iniciada");
    } catch (e) {
      toast.error(errMsg(e));
    }
  };

  return (
    <>
      <Link href="/agents" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Agentes IA</Link>
      <PageHeader title={agent.data?.name ?? "Agente"}>
        {form && <Button onClick={save} disabled={saving}><Save /> {saving ? "Salvando…" : "Salvar"}</Button>}
      </PageHeader>
      {agent.error && <ErrorBox message={agent.error} />}
      {(agent.loading || catalog.loading) && <Loading />}
      {stale > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          <TriangleAlert className="size-4 text-amber-600" />
          O modelo de embedding mudou: {stale} trecho(s) da base de conhecimento estão desatualizados e a busca não funciona bem até reindexar.
          <Button size="sm" onClick={reindex}>Reindexar</Button>
        </div>
      )}
      {saveError && <div className="mb-4"><ErrorBox message={saveError} /></div>}
      {form && catalog.data && (
        <Tabs defaultValue="rules">
          <TabsList>
            <TabsTrigger value="rules">Regras</TabsTrigger><TabsTrigger value="models">Modelos</TabsTrigger>
            <TabsTrigger value="knowledge">Conhecimento</TabsTrigger><TabsTrigger value="test">Testar</TabsTrigger>
          </TabsList>

          <TabsContent value="rules" className="mt-4 grid gap-4">
            <Field label="Nome do agente"><Input value={form.name} onChange={(e) => set({ name: e.target.value })} /></Field>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Saudação" hint="Primeira frase dita ao atender."><Textarea rows={3} value={form.greeting} onChange={(e) => set({ greeting: e.target.value })} /></Field>
              <Field label="Aviso de gravação (LGPD)" hint="Dito logo após a saudação."><Textarea rows={3} value={form.recording_notice} onChange={(e) => set({ recording_notice: e.target.value })} /></Field>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="rules.md (Markdown)">
                <Textarea className="h-[28rem] font-mono text-xs" spellCheck={false} value={form.rules_md} onChange={(e) => set({ rules_md: e.target.value })} />
              </Field>
              <div className="grid gap-1.5 text-sm font-medium">
                Pré-visualização
                <div className="h-[28rem] overflow-y-auto rounded-lg border p-4 text-sm [&_h1]:mb-3 [&_h1]:text-xl [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:mt-4 [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:mt-3 [&_h3]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_ol_li]:list-decimal [&_p]:my-2 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_strong]:font-semibold">
                  <Markdown>{form.rules_md}</Markdown>
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="models" className="mt-4 grid gap-4">
            <Card>
              <CardHeader><CardTitle>Modo de voz</CardTitle></CardHeader>
              <CardContent className="grid gap-4">
                <NativeSelect aria-label="Modo de voz" value={form.voice_mode} onChange={(e) => set({ voice_mode: e.target.value as Form["voice_mode"] })}>
                  <option value="pipeline">Pipeline (STT → LLM → TTS)</option>
                  <option value="realtime">Speech-to-speech (realtime)</option>
                </NativeSelect>
                <div className="grid gap-2">
                  <span className="text-sm font-medium">Realtime</span>
                  <p className="text-sm text-muted-foreground">Só o primeiro item é usado: sem fallback no meio da chamada; se falhar ao iniciar, usa o pipeline. No modo realtime, o TTS ainda fala frases fixas (como o aviso de gravação) e o pipeline serve de reserva.</p>
                  <ProviderList id="realtime" minRows={0} rows={form.realtime} catalog={catalog.data.providers.realtime ?? {}} onChange={(realtime) => set({ realtime })} />
                </div>
              </CardContent>
            </Card>
            {KINDS.map((k) => (
              <Card key={k}>
                <CardHeader><CardTitle>{KIND[k]}</CardTitle><p className="text-sm text-muted-foreground">A ordem define o fallback: se o primeiro falhar, tenta o próximo.</p></CardHeader>
                <CardContent><ProviderList id={k} rows={form[k]} catalog={catalog.data!.providers[k]} onChange={(rows) => set({ [k]: rows })} /></CardContent>
              </Card>
            ))}
            <Card>
              <CardHeader><CardTitle>Embedding e busca</CardTitle></CardHeader>
              <CardContent className="grid gap-4">
                <SingleProvider id="emb" row={form.embedding} catalog={catalog.data.providers.embedding} onChange={(embedding) => set({ embedding })} />
                <Field label={`Score mínimo de relevância: ${form.rag_min_score.toFixed(2)}`} hint="Trechos abaixo deste valor são ignorados pelo agente.">
                  <input type="range" min={0} max={1} step={0.01} value={form.rag_min_score} onChange={(e) => set({ rag_min_score: Number(e.target.value) })} />
                </Field>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="knowledge" className="mt-4"><KnowledgeTab agentId={Number(id)} /></TabsContent>

          <TabsContent value="test" className="mt-4">
            <Card>
              <CardHeader><CardTitle>Testar no navegador</CardTitle></CardHeader>
              <CardContent className="grid gap-3 text-sm">
                <p className="text-muted-foreground">Fala com o agente pelo microfone, sem passar pelo telefone. Salve as alterações antes de testar.</p>
                <div><TestCallButton target={{ agent_id: Number(id) }} label={`Agente ${form.name}`} /></div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      )}
    </>
  );
}
