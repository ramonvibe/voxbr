"""Mede a latência de voz real: fala sintetizada entra como microfone; mede do fim da fala do cliente até o
primeiro áudio do agente. Inclui rede até o LiveKit Cloud, como numa ligação de verdade.

Pré-requisitos: worker rodando (`apps/agent/main.py dev`), .env com LIVEKIT_* e OPENAI_API_KEY.
Uso: .venv/bin/python scripts/latency_bench.py <number_id> ["frase 1" "frase 2" ...]
"""

import asyncio
import json
import os
import statistics
import sys
import time

import numpy as np
from dotenv import load_dotenv
from livekit import api, rtc
from openai import AsyncOpenAI

load_dotenv()
RATE = 24000
FRAME = RATE // 100  # 10 ms
SPEECH_RMS = 300  # limiar de "tem voz" no áudio do agente (int16)
DEFAULT_PHRASES = ["Oi, bom dia!", "Quanto custa uma limpeza?", "Vocês atendem pela Amil Dental?"]


async def synth(text: str) -> np.ndarray:
    res = await AsyncOpenAI().audio.speech.create(
        model="gpt-4o-mini-tts", voice="alloy", input=text, response_format="pcm",
        instructions="Fale em português do Brasil, natural, como numa ligação.")
    return np.frombuffer(res.content, dtype=np.int16)


def token(room: str, number_id: int) -> str:
    return (api.AccessToken().with_identity("bench").with_grants(api.VideoGrants(room_join=True, room=room))
            .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(
                agent_name="voxbr", metadata=json.dumps({"number_id": number_id}))]))
            .to_jwt())


async def main(number_id: int, phrases: list[str]) -> None:
    clips = await asyncio.gather(*(synth(p) for p in phrases))
    room = rtc.Room()
    source = rtc.AudioSource(RATE, 1)
    outgoing: asyncio.Queue = asyncio.Queue()  # frames da fala do "cliente"; vazio = silêncio
    last_agent_voice = [0.0]
    first_voice_after: dict[str, float] = {}
    marker = {"t_end": None}

    async def watch(track: rtc.Track) -> None:
        async for ev in rtc.AudioStream(track):
            samples = np.frombuffer(ev.frame.data, dtype=np.int16)
            if samples.size and np.sqrt(np.mean(samples.astype(np.float32) ** 2)) > SPEECH_RMS:
                now = time.perf_counter()
                last_agent_voice[0] = now
                if marker["t_end"] and "t" not in first_voice_after:
                    first_voice_after["t"] = now

    @room.on("track_subscribed")
    def _on_track(track, pub, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            asyncio.ensure_future(watch(track))

    room_name = f"bench-{int(time.time())}"
    await room.connect(os.environ["LIVEKIT_URL"], token(room_name, number_id))
    await room.local_participant.publish_track(
        rtc.LocalAudioTrack.create_audio_track("mic", source),
        rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))

    async def feeder():
        """Único escritor do AudioSource: fala da fila ou silêncio (o VAD do agente precisa do silêncio)."""
        silent = rtc.AudioFrame(b"\0\0" * FRAME, RATE, 1, FRAME)
        while True:
            frame = silent if outgoing.empty() else outgoing.get_nowait()
            await source.capture_frame(frame)

    pump = asyncio.create_task(feeder())

    async def wait_agent_quiet(quiet_s: float = 1.5, timeout: float = 40):
        start = time.perf_counter()
        await asyncio.sleep(1)
        while time.perf_counter() - start < timeout:
            if last_agent_voice[0] and time.perf_counter() - last_agent_voice[0] > quiet_s:
                return
            await asyncio.sleep(0.1)

    await wait_agent_quiet(2.0, 60)  # aviso LGPD + saudação
    results = []
    for phrase, clip in zip(phrases, clips):
        for i in range(0, len(clip) - FRAME + 1, FRAME):
            outgoing.put_nowait(rtc.AudioFrame(clip[i:i + FRAME].tobytes(), RATE, 1, FRAME))
        while not outgoing.empty():
            await asyncio.sleep(0.005)
        await asyncio.sleep(source.queued_duration)  # o que ainda está no buffer do AudioSource
        first_voice_after.clear()
        marker["t_end"] = time.perf_counter()
        for _ in range(150):  # até 15 s
            if "t" in first_voice_after:
                break
            await asyncio.sleep(0.1)
        latency = first_voice_after["t"] - marker["t_end"] if "t" in first_voice_after else None
        marker["t_end"] = None
        results.append(latency)
        print(f"  {phrase:40} {'sem resposta' if latency is None else f'{latency:.2f}s'}")
        await wait_agent_quiet()
    valid = [r for r in results if r is not None]
    if valid:
        print(f"  mediana {statistics.median(valid):.2f}s  (min {min(valid):.2f}s, max {max(valid):.2f}s)")
    pump.cancel()
    await room.disconnect()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]), sys.argv[2:] or DEFAULT_PHRASES))
