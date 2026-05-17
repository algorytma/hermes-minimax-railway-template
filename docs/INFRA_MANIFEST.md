# Hermes-MiniMax Infrastructure Manifest & Architecture (v1.5)

This document serves as the **Single Source of Truth** for the Hermes agent's custom architecture. 
It is read by:
1. **Developer Agents (IDE)**: To understand the architectural blueprint before writing code.
2. **Runtime AI (Hermes)**: To perform "AI Impact Analysis" during upstream version upgrades.

During any system update or development session, these components must be preserved or adapted carefully.

---

## 1. Project Identity & Versioning
- **Current Core Version**: Tracked via `ARG HERMES_REF` in the root `Dockerfile`.
- **Purpose**: A specialized Hermes Agent template optimized for Railway deployment with native MiniMax support, multi-model fallback, and a robust persistent file system.
- **Repositories**:
  - **Core Agent**: `NousResearch/hermes-agent`
  - **Media MCP**: `algorytma/MiniMax-MCP-JS` (Custom JS Fork)
  - **This Template**: `algorytma/hermes-minimax-railway-template`

---

## 2. Persistence Map & Config Merge Strategy
The system runs in an ephemeral Railway Docker container. **ALL data must be persisted to `/data` (`HERMES_HOME`).**
- **Working Directory**: `/data/.hermes/`
- **config.yaml**: Managed via `server.py` using **PyYAML deep merge**. Manual edits to `config.yaml` are preserved. The system prompt is no longer in `config.yaml`.
- **SOUL.md**: Resides at `/data/.hermes/SOUL.md` (Slot #1 for the system prompt).
- **.env**: Contains system-level environment variables (e.g., API keys, Tokens). Excluded from git.
- **State & Checkpoints**: `/data/.hermes/state.db` and `/data/.hermes/checkpoints/`
- **mcp-output**: `/data/.hermes/mcp-output/` (Bypasses API 5-minute URL expiry for media).

### Manifest Seeding (`INFRA_MANIFEST.md`)
On startup, `server.py` checks for `/data/.hermes/docs/INFRA_MANIFEST.md`. If missing, it copies it from `/app/docs/` (the Docker image). This ensures the agent always has self-awareness without overwriting user changes.

---

## 3. Second Brain (PKB Sync) & Workspace
The agent operates within a dedicated workspace that is continuously synced with a private GitHub repository (e.g., an Obsidian Vault) to act as a "Second Brain".
- **Path**: `/data/.hermes/workspace/`
- **Structure**: 
  - `knowledge_base/`: Domain knowledge for the agent.
  - `projects/`: Where code and outputs are generated.
  - `private/`: User's private notes (Ignored by the agent).
  - `AGENTS.md` / `hermes.md`: Directives and indexes.
- **Daemon (`pkb_sync_loop`)**: An async task in `server.py` that runs every `PKB_SYNC_INTERVAL` minutes, committing changes and pulling (`--no-rebase`) via `GITHUB_TOKEN` to ensure a 2-Way Git sync.

---

## 4. The Hybrid "Highway" MCP Solution & Token Plan
To bypass hardcoded model restrictions in the official Python MCP, a Hybrid Architecture is used:
1. **Research Node (Python)**: `uvx minimax-coding-plan-mcp` (Handles Web Search and Vision).
2. **Media Node (Custom JS Fork)**: `npx -y algorytma/MiniMax-MCP-JS` (Handles TTS, Video, Music). This fork strips enum validations and allows dynamic model injection.

**Daily Quotas (Token Plan Max):**
- **Research / VLM**: 15,000 per 5 hours.
- **Video (`Hailuo-2.3-Fast-768P-6s`)**: STRICTLY 2 per day.
- **Music (`music-2.6`)**: 100 per day.
- **TTS (`speech-2.8-hd`)**: 11,000 per day.
*Agent Directive*: Plan generation calls efficiently. If quotas exceed, fallback models must be used gracefully without hallucinating external tools.

---

## 5. Brain Editor & File System
The custom web dashboard includes a mobile-native "Brain Editor".
- **`resolve_path` Aliases**:
  - `@DATA` -> `/data/.hermes`
  - `@WORKSPACE` -> `/data/.hermes/workspace`
  - `@PROMPTS` -> `/app/prompts`
  - `@ROOT` -> `/`
- Always use these aliases in the UI. E.g., The "Edit Manifest" button points to `@DATA/docs/INFRA_MANIFEST.md`.

---

## 6. Upgrades & Auto-Patching (GitHub API)
Upgrades are handled via the web UI without manual terminal intervention.
- **Mechanism**: The UI edits `/app/Dockerfile` locally and uses the `GITHUB_TOKEN` to push a commit (updating `ARG HERMES_REF=vX.Y.Z`) directly to the repository via the GitHub Contents API.
- **Trigger**: Railway detects the new commit and automatically initiates a redeployment.
- **Security**: `.gitignore` explicitly ignores `.hermes/`, `data/`, and `config.yaml` to prevent leaking secrets.

---

## 7. Known Bugs & System Limitations
- **Gateway External Restart BUG**: If the Hermes gateway is restarted natively (via Hermes' own UI or internal crash) rather than our Admin UI, our `Gateway` class reports an "error" state.
  - *Cause*: `_drain()` loses the stdout pipe when `--replace` creates a new process.
  - *Current Mitigation*: `server.py` attempts OS-level checks using `pgrep -f "hermes.*gateway"` and known PID files, but this occasionally fails inside the Railway container. 
  - *Note for Developers*: Do not rely solely on `self.proc.returncode`. If fixing, consider a polling healthcheck to a known local endpoint.
- **`display.personality` Warning**: The Hermes gateway may output a warning about missing `agent.personalities`. This is harmless; the merge logic correctly preserves user settings.
