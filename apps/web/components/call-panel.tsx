"use client";
import { ConnectionState } from "livekit-client";
import { useEffect, useRef } from "react";
import { LiveKitRoom, RoomAudioRenderer, useConnectionState, useLocalParticipant, useRemoteParticipants } from "@livekit/components-react";
import { Mic, MicOff, PhoneOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { LkToken } from "@/lib/types";

const STATE: Record<string, string> = {
  [ConnectionState.Connecting]: "Conectando…",
  [ConnectionState.Connected]: "Conectado",
  [ConnectionState.Reconnecting]: "Reconectando…",
  [ConnectionState.Disconnected]: "Desconectado",
};

function Controls({ hangupLabel, onHangup }: { hangupLabel: string; onHangup: () => void }) {
  const state = useConnectionState();
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="flex items-center gap-2 text-sm">
        <span className={`size-2 rounded-full ${state === ConnectionState.Connected ? "bg-emerald-500" : "bg-amber-500 animate-pulse"}`} />
        {STATE[state] ?? state}
      </span>
      <Button
        variant="outline"
        disabled={state !== ConnectionState.Connected}
        onClick={() => localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}
      >
        {isMicrophoneEnabled ? <Mic /> : <MicOff />} {isMicrophoneEnabled ? "Silenciar" : "Ativar microfone"}
      </Button>
      <Button variant="destructive" onClick={onHangup}><PhoneOff /> {hangupLabel}</Button>
    </div>
  );
}

/** Dispara uma vez quando todos os outros participantes saem (ex.: o cliente desligou). */
function OthersLeftWatcher({ onOthersLeft }: { onOthersLeft: () => void }) {
  const count = useRemoteParticipants().length;
  const seen = useRef(false);
  const fired = useRef(false);
  useEffect(() => {
    if (count > 0) seen.current = true;
    else if (seen.current && !fired.current) {
      fired.current = true;
      onOthersLeft();
    }
  }, [count, onOthersLeft]);
  return null;
}

/** Chamada de áudio no navegador (LiveKit).
 * `onHangup`: botão de desligar. `onEnded`: a conexão deste navegador caiu (não encerra a chamada do cliente).
 * `onOthersLeft`: todos os outros saíram da sala (ex.: o cliente desligou). */
export function CallPanel({ conn, hangupLabel, onHangup, onEnded, onOthersLeft }: {
  conn: LkToken; hangupLabel: string; onHangup: () => void; onEnded?: () => void; onOthersLeft?: () => void;
}) {
  return (
    <LiveKitRoom serverUrl={conn.server_url} token={conn.token} connect audio video={false} onDisconnected={onEnded}>
      <RoomAudioRenderer />
      {onOthersLeft && <OthersLeftWatcher onOthersLeft={onOthersLeft} />}
      <Controls hangupLabel={hangupLabel} onHangup={onHangup} />
    </LiveKitRoom>
  );
}
