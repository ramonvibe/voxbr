"use client";
import { createContext, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Bot, Clock, Headset, Hash, Inbox, LogOut, Moon, PhoneCall, Sun, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";
import { cn } from "@/lib/utils";

const MeCtx = createContext<Me | null>(null);
export const useMe = () => useContext(MeCtx)!;

const NAV = [
  { href: "/calls", label: "Chamadas", icon: PhoneCall, admin: true },
  { href: "/numbers", label: "Números", icon: Hash, admin: true },
  { href: "/agents", label: "Agentes IA", icon: Bot, admin: true },
  { href: "/queues", label: "Filas", icon: Clock, admin: true },
  { href: "/users", label: "Usuários", icon: Users, admin: true },
  { href: "/messages", label: "Recados", icon: Inbox, admin: false },
  { href: "/console", label: "Console", icon: Headset, admin: false },
];

export function homeFor(me: Me) {
  return me.role === "admin" ? "/calls" : "/console";
}

export function Shell({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me>();
  const path = usePathname();
  const router = useRouter();

  useEffect(() => {
    api<Me>("/auth/me").then(setMe).catch(() => {});
  }, []);

  // Atendente não acessa páginas de admin.
  useEffect(() => {
    if (me && me.role !== "admin" && NAV.some((n) => n.admin && path.startsWith(n.href))) router.replace(homeFor(me));
  }, [me, path, router]);

  if (!me) return <div className="grid min-h-screen place-items-center text-sm text-muted-foreground">Carregando…</div>;

  const items = NAV.filter((n) => me.role === "admin" || !n.admin);
  const toggleTheme = () => {
    const dark = document.documentElement.classList.toggle("dark");
    try { localStorage.theme = dark ? "dark" : "light"; } catch {}
  };
  const logout = async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    // navegação completa de propósito: zera todo o estado do cliente
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  };

  return (
    <MeCtx.Provider value={me}>
      <div className="flex min-h-screen">
        <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r bg-sidebar p-3 text-sidebar-foreground">
          <div className="mb-4 flex items-center gap-2 px-2 py-1 text-lg font-semibold"><PhoneCall className="size-5" /> voxbr</div>
          <nav className="flex flex-1 flex-col gap-1">
            {items.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm hover:bg-sidebar-accent",
                  path.startsWith(href) && "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
                )}
              >
                <Icon className="size-4" /> {label}
              </Link>
            ))}
          </nav>
          <div className="border-t pt-3">
            <div className="truncate px-2 text-sm font-medium">{me.name}</div>
            <div className="truncate px-2 pb-2 text-xs text-muted-foreground">{me.email}</div>
            <div className="flex gap-1">
              <Button variant="ghost" size="sm" className="flex-1 justify-start" onClick={logout}><LogOut /> Sair</Button>
              <Button variant="ghost" size="icon-sm" onClick={toggleTheme} aria-label="Alternar tema">
                <Sun className="hidden dark:block" /><Moon className="dark:hidden" />
              </Button>
            </div>
          </div>
        </aside>
        <main className="min-w-0 flex-1 p-6 lg:p-8"><div className="mx-auto max-w-6xl">{children}</div></main>
      </div>
    </MeCtx.Provider>
  );
}
