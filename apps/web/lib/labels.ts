export const STATUS: Record<string, string> = {
  ai: "Com IA", waiting_human: "Aguardando atendente", with_human: "Com atendente", ended: "Encerrada",
};
export const REASON: Record<string, string> = {
  customer_request: "Cliente pediu", out_of_scope: "Fora do escopo", no_answer: "Sem resposta na base",
  provider_failure: "Falha de provedor",
};
export const DAY: Record<string, string> = {
  mon: "Segunda", tue: "Terça", wed: "Quarta", thu: "Quinta", fri: "Sexta", sat: "Sábado", sun: "Domingo",
};
export const MODE: Record<string, string> = { ai: "IA atende", human_direct: "Direto para fila" };
export const ROLE: Record<string, string> = { admin: "Administrador", attendant: "Atendente" };
export const KIND: Record<string, string> = { stt: "Transcrição (STT)", llm: "Modelo de linguagem (LLM)", tts: "Voz (TTS)" };

export const usd = (v: number | null | undefined) => (v == null ? "—" : `US$ ${v.toFixed(4)}`);
export const dt = (s: string | null | undefined) => (s ? new Date(s).toLocaleString("pt-BR") : "—");
export function duration(a: string, b: string | null) {
  const s = Math.max(0, Math.round(((b ? new Date(b) : new Date()).getTime() - new Date(a).getTime()) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
