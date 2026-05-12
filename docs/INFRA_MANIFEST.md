# Hermes-MiniMax Infrastructure Manifest

This document serves as the definitive reference for the agent's custom architecture. During any upstream version upgrade, the agent must ensure these components are preserved or adapted.

## 1. Project Identity & Versioning
- **Current Core Version**: Tracked via `ARG HERMES_REF` in `Dockerfile`.
- **Purpose**: A specialized Hermes Agent template optimized for Railway deployment with native MiniMax support and multi-model fallback.

## 2. Critical Configuration Files
- **Path**: `/data/.hermes/` (Persistent Railway Volume)
- **config.yaml**: Managed via `server.py`. Contains MCP server definitions and personality settings. Must use **non-destructive deep merge** logic.
- **auth.json**: Stores provider credentials. Must be protected during upgrades.
- **.env**: System-level environment variables.

## 3. Custom Logic (Monkey-Patches)
- **Config Persistence**: `server.py` -> `write_config_yaml()`. Prevents UI updates from wiping custom MCP servers.
- **Encoding Robustness**: `server.py` implements a fallback chain (UTF-8 -> CP1254 -> Replace) to prevent crashes on Turkish characters or legacy logs.
- **Model Fallback**: Support for `LLM_FALLBACK_*` variables to enable automatic failover between providers.

## 4. MiniMax Integration
- **Research MCP**: Custom node for MiniMax search, video, and TTS.
- **Token Plan Optimization**: Logic to ensure the agent uses the MiniMax plan correctly without hitting rate limits unnecessarily.

## 5. Persistence Map
- `/data/.hermes/state.db`: Session history.
- `/data/.hermes/checkpoints/`: Agent state snapshots.
- `/data/.hermes/docs/`: Custom knowledge base.

---
*Note to Agent: Before performing an upgrade, compare the upstream changelog against these points. If a change affects any of these, prepare a patch before proceeding.*
