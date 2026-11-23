import { Badge } from "@/components/ui/badge";
import { STATUS } from "@/lib/labels";
import { cn } from "@/lib/utils";

const tone: Record<string, string> = {
  ai: "bg-blue-500/15 text-blue-700 dark:text-blue-300",
  waiting_human: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  with_human: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  ended: "bg-muted text-muted-foreground",
};
export function StatusBadge({ status }: { status: string }) {
  return <Badge variant="secondary" className={cn(tone[status])}>{STATUS[status] ?? status}</Badge>;
}
