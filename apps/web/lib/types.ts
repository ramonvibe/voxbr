export type Role = "admin" | "attendant";
export interface Me { id: number; email: string; name: string; role: Role; active: boolean; queue_ids: number[] }
export interface Provider { vendor: string; model: string; options: Record<string, unknown> }
export interface Agent {
  id: number; name: string; rules_md: string; greeting: string; recording_notice: string; language: string;
  voice_mode: "pipeline" | "realtime"; realtime: Provider[]; stt: Provider[]; llm: Provider[]; tts: Provider[]; embedding: Provider; rag_min_score: number;
  document_count: number; stale_chunks?: number;
}
export type AgentBody = Omit<Agent, "id" | "document_count" | "stale_chunks">;
export interface Doc { id: number; name: string; source: string; status: "processing" | "ready" | "error"; error: string | null; chunk_count: number; created_at: string }
export interface SearchHit { text: string; score: number; relevant: boolean }
export interface Hours { tz?: string; days?: Record<string, [string, string][]> }
export interface Queue { id: number; name: string; hours: Hours; holidays: string[]; wait_timeout_s: number; member_ids: number[] }
export interface User { id: number; email: string; name: string; role: Role; active: boolean; queue_ids: number[] }
export interface NumberRow {
  id: number; did: string; label: string; mode: "ai" | "human_direct"; agent_id: number | null; queue_id: number | null;
  retention_days: number; active: boolean; agent_name: string | null; queue_name: string | null;
}
export type CallStatus = "ai" | "waiting_human" | "with_human" | "ended";
export interface Turn { role: string; text: string; at?: string }
export interface Usage { type: string; provider?: string; model?: string; cost_usd: number | null; [k: string]: unknown }
export interface Call {
  id: number; room: string; did: string; caller: string; status: CallStatus; transfer_reason: string | null;
  summary: string | null; waiting_since?: string | null; cost_usd: number | null; started_at: string; ended_at: string | null;
  number_label: string; agent_name: string; queue_name: string; attendant_name: string;
  transcript?: Turn[]; usage?: Usage[];
}
export interface Msg { id: number; call_id: number | null; name: string; callback_number: string; message: string; done: boolean; created_at: string; queue_name: string }
export interface Catalog { providers: Record<"stt" | "llm" | "tts" | "embedding" | "realtime", Record<string, string[]>>; reasons: string[]; days: string[] }
export interface LkToken { server_url: string; token: string; room: string }
