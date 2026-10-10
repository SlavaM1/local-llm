#!/bin/sh
set -eu

BASE_MODEL="qwen3:8b"
OPTIMIZED_MODEL="qwen3-dev:8b"
MODELFILE="/models/qwen3-dev-optimized.Modelfile"

if ! ollama show "$BASE_MODEL" >/dev/null 2>&1; then
  echo "Pulling $BASE_MODEL (first start only)..."
  ollama pull "$BASE_MODEL"
else
  echo "$BASE_MODEL is already available."
fi

if ! ollama show "$OPTIMIZED_MODEL" >/dev/null 2>&1; then
  echo "Creating $OPTIMIZED_MODEL from the existing base model..."
  ollama create "$OPTIMIZED_MODEL" -f "$MODELFILE"
else
  echo "$OPTIMIZED_MODEL is already available."
fi

ollama show "$BASE_MODEL"
ollama show "$OPTIMIZED_MODEL"
