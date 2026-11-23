"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    api<Me>("/auth/me").then((m) => router.replace(m.role === "admin" ? "/calls" : "/console")).catch(() => {});
  }, [router]);
  return null;
}
