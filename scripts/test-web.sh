#!/usr/bin/env bash
# Abre uma chamada de teste no navegador com o agente voxbr.
# Pré-requisito: o worker rodando (.venv/bin/python apps/agent/main.py dev).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
# Sala nova a cada teste: o despacho do agente pelo token só ocorre quando a sala é criada.
lk token create --join --open meet --agent voxbr --room "teste-$(date +%s)" --identity voce --valid-for 1h
