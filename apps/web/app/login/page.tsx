"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { PhoneCall } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Field, ErrorBox } from "@/components/state";
import { api, errMsg } from "@/lib/api";
import type { Me } from "@/lib/types";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const me = await api<Me>("/auth/login", { method: "POST", json: { email, password } });
      router.replace(me.role === "admin" ? "/calls" : "/console");
    } catch (err) {
      setError(errMsg(err));
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl"><PhoneCall className="size-5" /> voxbr</CardTitle>
          <p className="text-sm text-muted-foreground">Entre para acessar o painel.</p>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid gap-4">
            <Field label="E-mail"><Input type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
            <Field label="Senha"><Input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
            {error && <ErrorBox message={error} />}
            <Button type="submit" disabled={busy}>{busy ? "Entrando…" : "Entrar"}</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
