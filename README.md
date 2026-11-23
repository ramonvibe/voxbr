# voxbr

> [!WARNING]
> **Projeto descartado.** O desenvolvimento foi encerrado e o código não recebe mais manutenção. Fica público só como referência.

Atendimento telefônico por IA em PT-BR. Cada número (DID) aponta para um agente de IA, com regras e base de conhecimento próprias, e para uma fila de atendentes humanos. O operador configura tudo pelo painel web.

Estado: **MVP pré-Sonax**. Funciona com navegador e número de teste. A ligação com os números e as filas da Sonax ainda depende das respostas do suporte deles.

## Como funciona

```
Cliente ─(telefone ou navegador)─> LiveKit Cloud ─> worker de voz (apps/agent)
                                                     ├─ STT → LLM → TTS  ou  speech-to-speech (realtime)
                                                     ├─ search_knowledge: RAG no Postgres/pgvector
                                                     ├─ transfer_to_human: fila web → atendente entra na sala, IA sai
                                                     └─ take_message: recado fora do horário / sem atendente
Painel (apps/web, Next.js) ─> API (apps/api, FastAPI) ─> Postgres
```

- **Agentes de IA:** cada um tem regras escritas em markdown no painel (o "rules.md"), saudação, aviso LGPD e modelos. Os modelos são STT, LLM e TTS em lista, com fallback na ordem, ou um modelo realtime. Cada agente tem também a sua base de conhecimento.
- **Regras fixas da plataforma**, que valem acima das do operador e ficam em `PLATFORM_RULES`, em `apps/agent/main.py`:
  - responder só com base na busca;
  - transferir quando não souber, quando o assunto estiver fora do escopo ou quando o cliente pedir;
  - nunca pedir senha ou dados de cartão.
- **Números:** modo `ai` (a IA atende e pode transferir para a fila do número) ou `human_direct` (a chamada vai direto para a fila).
- **Filas:** horário por dia da semana, feriados, tempo máximo de espera e atendentes. Fora do horário, ou se ninguém atender a tempo, a IA oferece deixar recado.
- **Transbordo:** a IA chama `transfer_to_human` com o motivo e um resumo. O cliente ouve um aviso fixo e música de espera. A chamada aparece no Console com o resumo e a transcrição. Quando o atendente clica em "Atender", ele entra na chamada pelo navegador e a IA sai.
- **LGPD:**
  - aviso de gravação e de IA no início, sem possibilidade de interrupção;
  - mascaramento de CPF, CNPJ, cartão, e-mail, telefone e CEP nos logs (`core/lgpd.py`);
  - retenção configurável por número, com expurgo via `python -m core.lgpd`, para rodar diariamente no cron.
- **Custo:** o uso de cada provedor multiplicado por `config/prices.yaml`. **Os preços desse arquivo são de referência e não foram conferidos.**

## Pré-requisitos

- Python 3.12+, Node 20+ com pnpm, Docker
- Conta no LiveKit Cloud e chave da OpenAI. A chave do Google só é necessária para usar os modelos do Google.
- `.env` preenchido a partir do `.env.example`

## Rodar

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python apps/agent/main.py download-files
(cd apps/web && pnpm install)
scripts/dev.sh        # Postgres + API :8000 + worker + painel :3000
```

Abra http://localhost:3000 e entre com `ADMIN_EMAIL`/`ADMIN_PASSWORD` do `.env`. O administrador é criado na primeira vez que a API sobe.

- **Administradores** veem Chamadas, Números, Agentes IA, Filas, Usuários, Recados e Console.
- **Atendentes** veem só Console e Recados.

O Next faz proxy de `/api/*` para a porta 8000.

## Testar

- **Pelo painel:** use o botão "Testar no navegador" na lista de números ou na página do agente.
- **Por telefone:** o número de teste dos EUA precisa estar ligado à regra de despacho `voxbr` no painel do LiveKit (Telephony > Phone Numbers > ⋮ > Assign dispatch rule).
- **Transbordo de ponta a ponta, sem microfone:** `.venv/bin/python scripts/smoke_handoff.py <id-do-número>`. Precisa da API e do worker rodando.
- **Testes automatizados:** `.venv/bin/python -m pytest`. Usam o banco `voxbr_test`, separado.

Para receber chamadas de um número +55 (Twilio ou Telnyx):
1. No provedor, aponte o número para `<subdominio>.sip.livekit.cloud`.
2. Rode `lk sip inbound create sip/inbound-trunk.json`.
3. Rode `lk sip dispatch create sip/dispatch-rule.json --trunks <id>`.

## Evals

Conversas de teste em texto, rodadas contra qualquer combinação de LLM. Medem acerto (transbordo esperado e juiz LLM), taxa de transbordo, latência e custo:

```bash
.venv/bin/python -m evals.runner evals/suites/exemplo.yaml \
  --llm openai:gpt-4.1-mini --llm google:gemini-2.5-flash --judge openai:gpt-4.1
```

A suíte aponta para um agente do banco e usa as regras e a base dele. O relatório em JSON fica em `evals/reports/`.

Os evals cobrem o "cérebro" (LLM, regras, RAG e decisão de transbordo). STT, TTS e realtime não entram, porque o texto vai direto ao LLM. A latência de voz aparece no log do worker, nas métricas de cada turno.

## Estrutura

```
apps/agent/   worker de voz (LiveKit Agents): ferramentas, transbordo, gravação da chamada
apps/api/     API do painel e do console (FastAPI)
apps/web/     painel do operador e console do atendente (Next.js + Tailwind + shadcn/ui)
core/         modelo de dados, provedores (registry + fallback), RAG, transbordo, LGPD, custo, auth
evals/        runner, suítes e relatórios
sip/          tronco e regra de despacho do LiveKit
scripts/      dev.sh, test-web.sh, smoke_handoff.py
```

Trocar ou adicionar um fornecedor de IA é uma entrada em `core/providers/registry.py` (STT, LLM, TTS, realtime) ou em `core/embeddings.py`. Escolher qual fornecedor cada agente usa é configuração, feita no painel.
