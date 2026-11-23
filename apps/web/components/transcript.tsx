import type { Turn } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Conversa em balões: cliente à esquerda, IA à direita. */
export function Transcript({ turns }: { turns?: Turn[] }) {
  if (!turns?.length) return <p className="text-sm text-muted-foreground">Sem transcrição.</p>;
  return (
    <div className="grid gap-2">
      {turns.map((t, i) => {
        const customer = t.role === "user";
        return (
          <div key={i} className={cn("flex flex-col", customer ? "items-start" : "items-end")}>
            <span className="mb-0.5 text-xs text-muted-foreground">
              {customer ? "Cliente" : "Agente IA"}{t.at ? ` · ${new Date(t.at).toLocaleTimeString("pt-BR")}` : ""}
            </span>
            <div className={cn("max-w-[80%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm", customer ? "rounded-tl-sm bg-muted" : "rounded-tr-sm bg-primary text-primary-foreground")}>
              {t.text}
            </div>
          </div>
        );
      })}
    </div>
  );
}
