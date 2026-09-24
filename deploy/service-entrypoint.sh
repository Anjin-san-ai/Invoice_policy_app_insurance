#!/usr/bin/env bash
# Dispatch to one of the three services based on the SERVICE env var.
# Lets all three Azure Container Apps share one image without a command override.
set -euo pipefail

case "${SERVICE:-}" in
  neuro-san)
    exec python -m neuro_san.service.main_loop.server_main_loop --http_port "${PORT:-8080}"
    ;;
  nsflow)
    exec python -m uvicorn nsflow.backend.main:app --host 0.0.0.0 --port "${PORT:-4173}"
    ;;
  invoice-api)
    exec python -m uvicorn apps.invoice_to_pay.backend.app.main:app --host 0.0.0.0 --port "${PORT:-8095}"
    ;;
  *)
    echo "Set SERVICE to one of: neuro-san | nsflow | invoice-api" >&2
    exit 1
    ;;
esac
