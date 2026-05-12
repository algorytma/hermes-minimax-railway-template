"""
Hermes Agent — Railway admin server.

Responsibilities:
  - Admin UI / setup wizard at /setup (Starlette + Jinja, cookie-auth guarded)
  - Management API at /setup/api/* (config, status, logs, gateway, pairing)
  - Reverse proxy at / and /* → native Hermes dashboard (hermes_cli/web_server, on 127.0.0.1:9119)
  - Managed subprocesses: `hermes gateway` (agent) and `hermes dashboard` (native UI)
  - Cookie-based session auth at /login (HMAC-signed, 7-day expiry, httponly)

Auth model: Basic Auth was dropped in favor of cookies because the Hermes React
SPA's plain fetch() calls do not reliably include basic-auth creds across browsers,
and basic-auth's per-directory protection space forced separate prompts for
/setup and /. Cookies auto-include on every same-origin request, so both the
setup UI and the proxied dashboard work with a single login. The cookie signing
secret is regenerated on every process start, so any ADMIN_PASSWORD change on
Railway (which triggers a redeploy) invalidates all existing sessions.

First-visit behavior: if no provider+model config exists, GET / redirects to /setup.
Once configured, / proxies to the Hermes dashboard. A small "← Setup" widget is
injected into every proxied HTML response so users can always return to the wizard.
"""

import asyncio
import json
import os
import re
import secrets
import signal
import time
import textwrap
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import yaml
import websockets
import websockets.exceptions
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from starlette.routing import Route, WebSocketRoute
from starlette.templating import Jinja2Templates
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

HERMES_HOME = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
ENV_FILE = Path(HERMES_HOME) / ".env"
PAIRING_DIR = Path(HERMES_HOME) / "pairing"
PAIRING_TTL = 3600

# Native Hermes dashboard — runs on loopback, fronted by our reverse proxy.
HERMES_DASHBOARD_HOST = "127.0.0.1"
HERMES_DASHBOARD_PORT = int(os.environ.get("HERMES_DASHBOARD_PORT", "9119"))
HERMES_DASHBOARD_URL = f"http://{HERMES_DASHBOARD_HOST}:{HERMES_DASHBOARD_PORT}"

# Mirror dashboard-ref-only/auth_proxy.py: strip only `host` (httpx sets it)
# and `transfer-encoding` (httpx recomputes it from the body). Keep everything
# else — notably `authorization`, because the SPA uses Bearer tokens against
# hermes's own /api/env/reveal and OAuth endpoints, and keep `cookie` since
# some hermes endpoints read it. Aggressive stripping was masking requests in
# ways that produced spurious 401s.
HOP_BY_HOP = {"host", "transfer-encoding"}

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
if not ADMIN_PASSWORD:
    ADMIN_PASSWORD = secrets.token_urlsafe(16)
    print(f"[server] Admin credentials — username: {ADMIN_USERNAME}  password: {ADMIN_PASSWORD}", flush=True)
else:
    print(f"[server] Admin username: {ADMIN_USERNAME}", flush=True)

# ── Env var registry ──────────────────────────────────────────────────────────
# (key, label, category, is_secret)
ENV_VARS = [
    ("LLM_MODEL",               "Model",                    "model",     False),
    ("LLM_FALLBACK_ENABLED",     "Enable Fallback",          "model",     False),
    ("LLM_FALLBACK_MODEL",       "Fallback Model",           "model",     False),
    ("LLM_FALLBACK_PROVIDER",    "Fallback Provider",        "model",     False),
    ("OPENROUTER_API_KEY",       "OpenRouter",               "provider",  True),
    ("DEEPSEEK_API_KEY",         "DeepSeek",                 "provider",  True),
    ("DASHSCOPE_API_KEY",        "DashScope",                "provider",  True),
    ("GLM_API_KEY",              "GLM / Z.AI",               "provider",  True),
    ("KIMI_API_KEY",             "Kimi",                     "provider",  True),
    ("MINIMAX_API_KEY",          "MiniMax",                  "provider",  True),
    ("HF_TOKEN",                 "Hugging Face",             "provider",  True),
    # Added in v2026.4.23 (hermes v0.11.0). All plain API-key auth — hermes
    # auto-routes by env-var presence, no extra config needed on our side.
    # OAuth-based providers (Gemini CLI, Qwen OAuth, Claude Code, Copilot)
    # are reachable via the dashboard's Keys tab and not exposed here.
    ("NVIDIA_API_KEY",           "NVIDIA NIM",               "provider",  True),
    ("ARCEE_API_KEY",            "Arcee AI",                 "provider",  True),
    ("STEPFUN_API_KEY",          "Step Plan",                "provider",  True),
    ("AI_GATEWAY_API_KEY",       "Vercel AI Gateway",        "provider",  True),
    ("GEMINI_API_KEY",           "Google AI Studio",         "provider",  True),
    ("PARALLEL_API_KEY",         "Parallel (search)",        "tool",      True),
    ("FIRECRAWL_API_KEY",        "Firecrawl (scrape)",       "tool",      True),
    ("TAVILY_API_KEY",           "Tavily (search)",          "tool",      True),
    ("FAL_KEY",                  "FAL (image gen)",          "tool",      True),
    ("BROWSERBASE_API_KEY",      "Browserbase key",          "tool",      True),
    ("BROWSERBASE_PROJECT_ID",   "Browserbase project",      "tool",      False),
    ("GITHUB_TOKEN",             "GitHub token",             "tool",      True),
    ("VOICE_TOOLS_OPENAI_KEY",   "OpenAI (voice/TTS)",       "tool",      True),
    ("HONCHO_API_KEY",           "Honcho (memory)",          "tool",      True),
    ("TELEGRAM_BOT_TOKEN",       "Bot Token",                "telegram",  True),
    ("TELEGRAM_ALLOWED_USERS",   "Allowed User IDs",         "telegram",  False),
    ("DISCORD_BOT_TOKEN",        "Bot Token",                "discord",   True),
    ("DISCORD_ALLOWED_USERS",    "Allowed User IDs",         "discord",   False),
    ("SLACK_BOT_TOKEN",          "Bot Token (xoxb-...)",     "slack",     True),
    ("SLACK_APP_TOKEN",          "App Token (xapp-...)",     "slack",     True),
    ("WHATSAPP_ENABLED",         "Enable WhatsApp",          "whatsapp",  False),
    ("EMAIL_ADDRESS",            "Email Address",            "email",     False),
    ("EMAIL_PASSWORD",           "Email Password",           "email",     True),
    ("EMAIL_IMAP_HOST",          "IMAP Host",                "email",     False),
    ("EMAIL_SMTP_HOST",          "SMTP Host",                "email",     False),
    ("MATTERMOST_URL",           "Server URL",               "mattermost",False),
    ("MATTERMOST_TOKEN",         "Bot Token",                "mattermost",True),
    ("MATRIX_HOMESERVER",        "Homeserver URL",           "matrix",    False),
    ("MATRIX_ACCESS_TOKEN",      "Access Token",             "matrix",    True),
    ("MATRIX_USER_ID",           "User ID",                  "matrix",    False),
    ("GATEWAY_ALLOW_ALL_USERS",  "Allow all users",          "gateway",   False),
    ("ADMIN_USERNAME",           "Admin username",           "admin",     False),
    ("ADMIN_PASSWORD",           "Admin password",           "admin",     True),
    ("MINIMAX_TOKEN_PLAN_ENABLED", "Enable MiniMax Token Plan (Global)", "provider", False),
]

SECRET_KEYS  = {k for k, _, _, s in ENV_VARS if s}
PROVIDER_KEYS = [k for k, _, c, _ in ENV_VARS if c == "provider"]
CHANNEL_MAP  = {
    "Telegram":    "TELEGRAM_BOT_TOKEN",
    "Discord":     "DISCORD_BOT_TOKEN",
    "Slack":       "SLACK_BOT_TOKEN",
    "WhatsApp":    "WHATSAPP_ENABLED",
    "Email":       "EMAIL_ADDRESS",
    "Mattermost":  "MATTERMOST_TOKEN",
    "Matrix":      "MATRIX_ACCESS_TOKEN",
}


# ── .env helpers ──────────────────────────────────────────────────────────────
def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out = {}
    try:
        # Try UTF-8 first
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            # Fallback to Turkish Windows encoding
            content = path.read_text(encoding="cp1254")
        except UnicodeDecodeError:
            # Last resort: replace bad bytes
            content = path.read_text(encoding="utf-8", errors="replace")

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        out[k.strip()] = v
    return out


# ── SOUL.md — Hermes native agent identity ───────────────────────────────────
# Hermes reads $HERMES_HOME/SOUL.md as the agent's primary identity (slot #1 in
# the system prompt).  We seed this file once; if the user edits it, we never
# overwrite it — matching upstream Hermes behaviour.
SOUL_MD_CONTENT = textwrap.dedent("""\
    # Personality

    You are an expert Hermes AI assistant using the Official MiniMax Native Integration (Token Plan Max).

    ## Tool Model Mapping

    CRITICAL: Always explicitly specify these models when using tools:
    - Audio/TTS: "speech-2.8-hd"
    - Video: "Hailuo-2.3-Fast-768P-6s"
    - Music: "music-2.6"
    - Image: "image-01"

    ## Image Understanding

    When a user sends an image or asks you to analyze/describe an image:
    - ALWAYS use `mcp_minimax_research_understand_image` tool (MiniMax Research MCP)
    - NEVER use the builtin `vision_analyze` tool — our provider does not support multimodal via /v1
    - If `mcp_minimax_research_understand_image` fails, inform the user that image analysis is temporarily unavailable

    ## Error Handling

    If a tool fails with "plan support" error, retry once with model=null.

    ## Communication Style

    - Be direct and concise
    - Prefer substance over filler
    - Admit uncertainty plainly
    - Optimize for truth, clarity, and usefulness
""")


# Known Hermes default identity snippets — if SOUL.md contains one of these,
# it's the stock file and we should replace it with our custom identity.
_HERMES_DEFAULT_MARKERS = [
    "You are Hermes Agent, an intelligent AI assistant created by Nous Research",
    "You are helpful, knowledgeable, and direct",
]


def ensure_soul_md() -> None:
    """Seed SOUL.md with our custom identity.

    Hermes auto-creates a default SOUL.md on first boot.  We detect
    that stock file (by checking for known default markers) and replace
    it with our MiniMax-tailored identity.  If the user has customised
    SOUL.md (content differs from both our template and Hermes defaults),
    we leave it untouched.
    """
    soul_path = Path(HERMES_HOME) / "SOUL.md"
    if soul_path.exists():
        try:
            current = soul_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                current = soul_path.read_text(encoding="cp1254")
            except UnicodeDecodeError:
                current = soul_path.read_text(encoding="utf-8", errors="replace")

        # Check if it's the Hermes default — replace with ours
        is_hermes_default = any(marker in current for marker in _HERMES_DEFAULT_MARKERS)
        # Check if it's already our content
        is_ours = "MiniMax Native Integration" in current
        if is_ours:
            # v1.6: Update SOUL.md if it's missing the vision routing directive
            needs_vision_update = "mcp_minimax_research_understand_image" not in current
            if needs_vision_update:
                print("[server] Updating SOUL.md with vision routing directives.", flush=True)
                soul_path.write_text(SOUL_MD_CONTENT)
                return
            print("[server] SOUL.md already has custom identity — preserving.", flush=True)
            return
        if is_hermes_default:
            print("[server] Replacing Hermes default SOUL.md with custom identity.", flush=True)
            soul_path.write_text(SOUL_MD_CONTENT)
            return
        # Unknown custom content — user edited it, don't touch
        print("[server] SOUL.md has user-customised content — preserving.", flush=True)
        return
    soul_path.parent.mkdir(parents=True, exist_ok=True)
    soul_path.write_text(SOUL_MD_CONTENT)
    print("[server] Created SOUL.md with custom agent identity.", flush=True)


# ── Persistent agent docs under /data/.hermes/docs/ ──────────────────────────
# These files give the agent categorised self-knowledge it can read on demand
# without bloating the system prompt.  Each file covers one topic.

AGENT_DOCS: dict[str, tuple[str, str]] = {
    # (relative_path, content)  — relative to HERMES_HOME/docs/
    "infra/platform_info.md": (
        "Platform & infrastructure details",
        textwrap.dedent("""\
            # Platform & Infrastructure

            | Key | Value |
            |-----|-------|
            | Hosting | Railway (Docker container) |
            | Persistent Volume | `/data` — survives redeployments |
            | Working Directory | `/data/.hermes` |
            | Config File | `/data/.hermes/config.yaml` |
            | Agent Identity | `/data/.hermes/SOUL.md` (Hermes native, slot #1) |
            | API Key Injection | Railway env vars → `.env` file |
            | Docker Strategy | `HERMES_REF` build arg pins upstream version |
            | Admin UI | Custom Starlette wrapper at `/setup` |

            ## Key Directories
            - `/data/.hermes/mcp-output/` — Generated media files
            - `/data/.hermes/memories/` — Persistent memory (MEMORY.md, USER.md)
            - `/data/.hermes/sessions/` — Gateway session data
            - `/data/.hermes/docs/` — This documentation tree
        """)
    ),
    "model/model_routing.md": (
        "Model routing & Token Plan Max details",
        textwrap.dedent("""\
            # Model Routing & Token Plan Max

            ## Provider: MiniMax (Native)
            This agent uses the MiniMax Native Integration with Token Plan Max.
            The provider is set to `minimax` in config.yaml when MINIMAX_API_KEY is present.

            ## Authorised Media Models
            CRITICAL — always explicitly pass these model names to MCP tools:

            | Domain | Model | Fallback |
            |--------|-------|----------|
            | TTS | `speech-2.8-hd` | `speech-01` |
            | Video | `Hailuo-2.3-Fast-768P-6s` | `Hailuo-2.3-768P-6s` |
            | Music | `music-2.6` | `music-2.5` |
            | Lyrics | `lyrics_generation` | — |
            | Music Cover | `music-cover` | — |
            | Image | `image-01` | — |

            ## Daily Quotas
            | Domain | Model | Limit |
            |--------|-------|-------|
            | Research | `coding-plan-search` | 15,000 / 5h |
            | VLM | `coding-plan-vlm` | 15,000 / 5h |
            | Image | `image-01` | 120 / day |
            | TTS | `speech-2.8-hd` | 11,000 / day |
            | Music | `music-2.6` | 100 / day |
            | Music | `music-2.5` | 4 / day |
            | Video | `Hailuo-2.3-Fast-768P-6s` | 2 / day |
            | Video | `Hailuo-2.3-768P-6s` | 2 / day |
        """)
    ),
    "mcp/mcp_architecture.md": (
        "MCP server architecture (hybrid pipeline)",
        textwrap.dedent("""\
            # Hybrid MCP Architecture

            ## Research Node (Official Python)
            - Command: `uvx minimax-coding-plan-mcp`
            - Handles: Web Search, Vision/VLM (Image Understanding)
            - These tools work without model parameter conflicts.

            ## Media Node (Custom JS Fork)
            - Command: `npx -y algorytma/MiniMax-MCP-JS`
            - Handles: TTS, Video, Music, Image generation
            - Rigid enum validations removed; accepts any model string.
            - Local storage bypass: media saved to `/data/.hermes/mcp-output/`
            - Error reporting: returns exact API error with `isError: true` flag.

            ## Vision / Image Understanding
            - Tool: `mcp_minimax_research_understand_image` (via minimax-research MCP)
            - Model: `coding-plan-vlm` (15,000 daily quota / 5h cycle)
            - IMPORTANT: Do NOT use builtin `vision_analyze` — MiniMax /v1 is text-only
            - The builtin vision tool is disabled via `auxiliary.vision.provider: none`

            ## Error Handling
            If a tool returns a plan/support or quota error:
            1. Do NOT hallucinate external tools.
            2. Retry with the designated fallback model.
            3. If still failing, inform the user about quota limits.
        """)
    ),
    "history/project_origins.md": (
        "Repository lineage and upstream references",
        textwrap.dedent("""\
            # Project Origins & Repositories

            | Component | Repository | Role |
            |-----------|-----------|------|
            | Core Agent | `NousResearch/hermes-agent` | Intelligence & orchestration engine |
            | Media MCP | `algorytma/MiniMax-MCP-JS` | Custom JS fork — removed hardcoded models |
            | Base Template | `praveen-ks-2001/hermes-agent-template` | Original Railway wrapper |
            | This Repo | `algorytma/hermes-minimax-railway-template` | Unified production environment |

            ## Upgrade Strategy
            - `HERMES_REF` in Dockerfile pins the upstream agent version.
            - Default `main` = bleeding edge; set to tag (e.g. `v2026.4.23`) for stability.
            - Railway rollback: Deployments tab → find green badge → Redeploy.
            - `/data` volume is preserved during rollbacks.
        """)
    ),
}


def ensure_agent_docs() -> None:
    """Seed agent documentation files.  Existing files are never overwritten."""
    docs_dir = Path(HERMES_HOME) / "docs"
    created = 0
    for rel_path, (desc, content) in AGENT_DOCS.items():
        full_path = docs_dir / rel_path
        if full_path.exists():
            continue
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        created += 1
    if created:
        print(f"[server] Seeded {created} agent doc(s) under {docs_dir}", flush=True)


# ── config.yaml helpers ───────────────────────────────────────────────────────
def write_config_yaml(data: dict[str, str]) -> None:
    """Merge-write config.yaml: update model/provider/MCP settings while
    preserving user-customised keys (timezone, compression, etc.).

    Uses PyYAML to parse the existing file (if any) and deep-merge only the
    keys we own.  Everything else the user set via the Hermes dashboard or
    by hand-editing the file survives container restarts and redeployments.
    """
    model = data.get("LLM_MODEL", "")
    is_token_plan = data.get("MINIMAX_TOKEN_PLAN_ENABLED", "").lower() == "true"

    # Logic to force native provider if MiniMax key is present
    provider = "auto"
    if data.get("MINIMAX_API_KEY"):
        provider = "minimax"
        if model.startswith("minimax/"):
            model = model.replace("minimax/", "")

    config_path = Path(HERMES_HOME) / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Load existing config (preserve user settings) ─────────────────
    existing: dict = {}
    if config_path.exists():
        try:
            # Try UTF-8
            raw_config = config_path.read_text(encoding="utf-8")
            existing = yaml.safe_load(raw_config) or {}
        except (yaml.YAMLError, UnicodeDecodeError):
            try:
                # Fallback to Turkish Windows
                raw_config = config_path.read_text(encoding="cp1254")
                existing = yaml.safe_load(raw_config) or {}
            except Exception:
                print("[server] WARNING: config.yaml parse error — recreating.", flush=True)
                existing = {}

    # ── Model & provider (always overwrite — comes from admin UI) ─────
    existing.setdefault("model", {})
    existing["model"]["default"] = model
    existing["model"]["provider"] = provider

    # ── Fallback Model Support ───────────────────────────────────────
    fallback_enabled = data.get("LLM_FALLBACK_ENABLED", "").lower() == "true"
    fallback_model = data.get("LLM_FALLBACK_MODEL", "")
    fallback_prov_raw = data.get("LLM_FALLBACK_PROVIDER", "").lower()

    if fallback_enabled and fallback_model:
        # Map human-readable provider to hermes internal provider name
        f_provider = "auto"
        if "openrouter" in fallback_prov_raw: f_provider = "openrouter"
        elif "deepseek" in fallback_prov_raw: f_provider = "deepseek"
        elif "minimax" in fallback_prov_raw:  f_provider = "minimax"
        elif "google" in fallback_prov_raw or "gemini" in fallback_prov_raw: f_provider = "google"
        elif "dashscope" in fallback_prov_raw: f_provider = "dashscope"
        elif "glm" in fallback_prov_raw:       f_provider = "glm"
        elif "openai" in fallback_prov_raw:    f_provider = "openai"
        elif "anthropic" in fallback_prov_raw: f_provider = "anthropic"
        elif "nvidia" in fallback_prov_raw:    f_provider = "nvidia"
        
        existing["model"]["fallbacks"] = [
            {"model": fallback_model, "provider": f_provider}
        ]
    else:
        existing["model"].pop("fallbacks", None)

    # ── Terminal defaults (only if not yet set) ───────────────────────
    existing.setdefault("terminal", {})
    existing["terminal"].setdefault("backend", "local")
    existing["terminal"].setdefault("timeout", 60)
    existing["terminal"].setdefault("cwd", "/tmp")

    # ── Agent (official Hermes param name is max_turns, not max_iterations)
    existing.setdefault("agent", {})
    existing["agent"].setdefault("max_turns", 90)  # Hermes default
    # Clean up legacy param if present
    existing["agent"].pop("max_iterations", None)
    existing["agent"].pop("system_prompt", None)  # Moved to SOUL.md

    # ── data_dir ──────────────────────────────────────────────────────
    existing["data_dir"] = HERMES_HOME

    # ── MCP servers (Token Plan) ──────────────────────────────────────
    if is_token_plan:
        (Path(HERMES_HOME) / "mcp-output").mkdir(parents=True, exist_ok=True)
        existing.setdefault("mcp_servers", {})
        existing["mcp_servers"].update({
            "minimax-research": {
                "command": "uvx",
                "args": ["minimax-coding-plan-mcp"],
                "env": {
                    "MINIMAX_API_KEY": "${MINIMAX_API_KEY}",
                    "MINIMAX_API_HOST": "https://api.minimax.io",
                },
            },
            "minimax-media": {
                "command": "npx",
                "args": ["-y", "algorytma/MiniMax-MCP-JS"],
                "env": {
                    "MINIMAX_API_KEY": "${MINIMAX_API_KEY}",
                    "MINIMAX_API_HOST": "https://api.minimax.io",
                    "MINIMAX_MCP_BASE_PATH": "/data/.hermes/mcp-output",
                },
            },
        })

    # ── Auxiliary overrides (MiniMax text-only: disable builtin vision) ────
    # MiniMax /v1/chat/completions does not support multimodal input.
    # Vision is handled by minimax-research MCP (coding-plan-vlm model).
    if data.get("MINIMAX_API_KEY"):
        existing.setdefault("auxiliary", {})
        # Merge vision block instead of overwriting it if it exists
        vision_cfg = existing["auxiliary"].setdefault("vision", {})
        if isinstance(vision_cfg, dict):
            vision_cfg["provider"] = "none"
        else:
            # If it's something else (unlikely), force it
            existing["auxiliary"]["vision"] = {"provider": "none"}

    config_path.write_text(yaml.dump(existing, default_flow_style=False, sort_keys=False))
    print(f"[server] config.yaml updated (model={model}, provider={provider})", flush=True)


def write_env(path: Path, data: dict[str, str]) -> None:
    """Write sanitized vars to .env (for the gateway)."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # If Token Plan is enabled, force the Global API base for the LLM as well
    if data.get("MINIMAX_TOKEN_PLAN_ENABLED", "").lower() == "true":
        data["MINIMAX_API_BASE"] = "https://api.minimax.io/v1"

    cat_order = ["model", "provider", "tool",
                 "telegram", "discord", "slack", "whatsapp",
                 "email", "mattermost", "matrix", "gateway"]
    cat_labels = {
        "model": "Model", "provider": "Providers", "tool": "Tools",
        "telegram": "Telegram", "discord": "Discord", "slack": "Slack",
        "whatsapp": "WhatsApp", "email": "Email",
        "mattermost": "Mattermost", "matrix": "Matrix", "gateway": "Gateway",
    }
    key_cat = {k: c for k, _, c, _ in ENV_VARS}
    grouped: dict[str, list[str]] = {c: [] for c in cat_order}
    grouped["other"] = []

    for k, v in data.items():
        if not v:
            continue
        cat = key_cat.get(k, "other")
        grouped.setdefault(cat, []).append(f"{k}={v}")

    lines: list[str] = []
    for cat in cat_order:
        entries = sorted(grouped.get(cat, []))
        if entries:
            lines.append(f"# {cat_labels.get(cat, cat)}")
            lines.extend(entries)
            lines.append("")
    if grouped["other"]:
        lines.append("# Other")
        lines.extend(sorted(grouped["other"]))
        lines.append("")

    path.write_text("\n".join(lines))


def is_config_complete(data: dict[str, str] | None = None) -> bool:
    """Single source of truth for 'ready to run the gateway'.

    Used by: GET / redirect, auto_start on boot, admin API status.
    """
    if data is None:
        data = read_env(ENV_FILE)
    has_model = bool(data.get("LLM_MODEL"))
    has_provider = any(data.get(k) for k in PROVIDER_KEYS)
    return has_model and has_provider


def mask(data: dict[str, str]) -> dict[str, str]:
    return {
        k: (v[:8] + "***" if len(v) > 8 else "***") if k in SECRET_KEYS and v else v
        for k, v in data.items()
    }


def unmask(new: dict[str, str], existing: dict[str, str]) -> dict[str, str]:
    return {
        k: (existing.get(k, "") if k in SECRET_KEYS and v.endswith("***") else v)
        for k, v in new.items()
    }


# ── Auth (cookie-based) ───────────────────────────────────────────────────────
# We use HMAC-signed cookies instead of HTTP Basic Auth because:
#   1. Basic auth's per-directory protection space means browsers cache creds
#      for /setup/* separately from /*, forcing re-prompt on navigation.
#   2. Browser behavior for sending Basic auth on XHR/fetch is inconsistent;
#      the Hermes React SPA's plain fetch() calls don't reliably include it,
#      causing every proxied API call to 401.
# Cookies are auto-included on every same-origin request (navigation + XHR)
# so both the setup UI and the proxied Hermes dashboard work with one login.
#
# The SECRET is regenerated on every process start. That means any ADMIN_PASSWORD
# change via Railway → redeploy → all existing cookies invalidate → users re-login.
import hashlib as _hashlib
import hmac as _hmac
from urllib.parse import quote as _url_quote, urlparse as _urlparse

COOKIE_NAME = "hermes_auth"
COOKIE_MAX_AGE = 7 * 86400  # 7 days
COOKIE_SECRET = secrets.token_bytes(32)

# Public paths — no auth required. Everything else is behind the cookie gate.
PUBLIC_PATHS = {"/health", "/login", "/logout"}


def _make_auth_token() -> str:
    """Build a cookie value: `<expires>.<hmac-sha256>`."""
    expires = str(int(time.time()) + COOKIE_MAX_AGE)
    sig = _hmac.new(COOKIE_SECRET, expires.encode(), _hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def _verify_auth_token(token: str) -> bool:
    try:
        expires_s, sig = token.rsplit(".", 1)
        if int(expires_s) < time.time():
            return False
        expected = _hmac.new(COOKIE_SECRET, expires_s.encode(), _hashlib.sha256).hexdigest()
        return _hmac.compare_digest(sig, expected)
    except Exception:
        return False


def _is_authenticated(request: Request) -> bool:
    return _verify_auth_token(request.cookies.get(COOKIE_NAME, ""))


def _safe_return_to(value: str) -> str:
    """Reject open-redirect attempts - only allow same-origin relative paths."""
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/"
    # Strip any scheme/netloc that slipped through.
    p = _urlparse(value)
    if p.scheme or p.netloc:
        return "/"
    return value


def guard(request: Request) -> Response | None:
    """Enforce auth on protected routes.

    - HTML navigation: 302 to /login?returnTo=<path>
    - API / XHR: 401 JSON (so the SPA's fetch() can surface it cleanly)
    """
    if _is_authenticated(request):
        return None
    accept = request.headers.get("accept", "").lower()
    wants_html = "text/html" in accept
    if wants_html:
        rt = request.url.path
        if request.url.query:
            rt = f"{rt}?{request.url.query}"
        return RedirectResponse(f"/login?returnTo={_url_quote(rt)}", status_code=302)
    return JSONResponse({"error": "Unauthorized"}, status_code=401)


LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hermes Agent — Sign in</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0f14;color:#c9d1d9;font-family:'IBM Plex Sans',sans-serif;
  min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.card{background:#14181f;border:1px solid #252d3d;border-radius:12px;padding:36px 32px;width:100%;max-width:380px;
  box-shadow:0 20px 40px rgba(0,0,0,0.4)}
.brand{text-align:center;margin-bottom:28px}
.brand-logo{display:inline-flex;align-items:center;gap:10px;font-family:'IBM Plex Mono',monospace;font-weight:600;font-size:18px;color:#6272ff}
.brand-logo span{color:#6b7688;font-weight:400}
.brand-sub{font-family:'IBM Plex Mono',monospace;font-size:11px;color:#6b7688;margin-top:8px;letter-spacing:1.5px;text-transform:uppercase}
label{display:block;font-family:'IBM Plex Mono',monospace;font-size:11px;color:#6b7688;
  letter-spacing:0.05em;text-transform:uppercase;margin-bottom:6px;margin-top:16px}
input{width:100%;background:#0d0f14;border:1px solid #252d3d;border-radius:6px;color:#c9d1d9;
  font-family:'IBM Plex Mono',monospace;font-size:13px;padding:9px 11px;outline:none;transition:border-color .15s}
input:focus{border-color:#6272ff}
button{width:100%;margin-top:24px;background:#6272ff;border:1px solid #6272ff;border-radius:6px;color:#fff;
  font-family:'IBM Plex Mono',monospace;font-size:13px;font-weight:500;padding:10px;cursor:pointer;
  transition:background .15s,border-color .15s}
button:hover{background:#7b8fff;border-color:#7b8fff}
.err{background:rgba(248,81,73,0.08);border:1px solid rgba(248,81,73,0.3);border-radius:6px;
  color:#f85149;font-family:'IBM Plex Mono',monospace;font-size:12px;padding:8px 12px;margin-bottom:14px;text-align:center}
.footnote{margin-top:18px;font-family:'IBM Plex Mono',monospace;font-size:10px;color:#6b7688;text-align:center;line-height:1.6}
</style></head>
<body>
<div class="card">
  <div class="brand">
    <div class="brand-logo">hermes<span>/admin</span></div>
    <div class="brand-sub">Sign in to continue</div>
  </div>
  __ERROR__
  <form method="POST" action="/login">
    <input type="hidden" name="returnTo" value="__RETURN_TO__">
    <label for="username">Username</label>
    <input id="username" name="username" type="text" autocomplete="username" autofocus required>
    <label for="password">Password</label>
    <input id="password" name="password" type="password" autocomplete="current-password" required>
    <button type="submit">Sign in</button>
  </form>
  <p class="footnote">Credentials are the <code>ADMIN_USERNAME</code> and <code>ADMIN_PASSWORD</code><br>Railway service variables.</p>
</div>
</body></html>"""


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&#39;"))


async def page_login(request: Request) -> Response:
    """GET /login — render the sign-in form."""
    # Already signed in? Bounce to returnTo (or /).
    if _is_authenticated(request):
        return RedirectResponse(_safe_return_to(request.query_params.get("returnTo", "/")), status_code=302)
    rt = _safe_return_to(request.query_params.get("returnTo", "/"))
    error_html = ('<div class="err">Invalid username or password</div>'
                  if request.query_params.get("error") else "")
    html = (LOGIN_PAGE_HTML
            .replace("__ERROR__", error_html)
            .replace("__RETURN_TO__", _html_escape(rt)))
    return HTMLResponse(html)


async def login_post(request: Request) -> Response:
    """POST /login — validate creds and set the auth cookie."""
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))
    return_to = _safe_return_to(str(form.get("returnTo", "/")))

    valid_user = _hmac.compare_digest(username, ADMIN_USERNAME)
    valid_pw = _hmac.compare_digest(password, ADMIN_PASSWORD)
    if valid_user and valid_pw:
        resp = RedirectResponse(return_to, status_code=302)
        resp.set_cookie(
            COOKIE_NAME,
            _make_auth_token(),
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return resp
    return RedirectResponse(f"/login?returnTo={_url_quote(return_to)}&error=1", status_code=302)


async def logout(request: Request) -> Response:
    """GET /logout — clear cookie and bounce to login."""
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


# ── Gateway manager ───────────────────────────────────────────────────────────
class Gateway:
    def __init__(self):
        self.proc: asyncio.subprocess.Process | None = None
        self.state = "stopped"
        self.logs: deque[str] = deque(maxlen=500)
        self.started_at: float | None = None
        self.restarts = 0

    async def start(self):
        if self.proc and self.proc.returncode is None:
            return
        self.state = "starting"
        try:
            # .env values take priority over Railway env vars.
            # We build the env this way so hermes's own dotenv loading
            # (which reads the same file) doesn't shadow our values.
            env = {**os.environ, "HERMES_HOME": HERMES_HOME}
            env.update(read_env(ENV_FILE))
            model = env.get("LLM_MODEL", "")
            provider_key = next((env.get(k, "") for k in PROVIDER_KEYS if env.get(k)), "")
            print(f"[gateway] model={model or '⚠ NOT SET'} | provider_key={'set' if provider_key else '⚠ NOT SET'}", flush=True)
            # Seed SOUL.md (agent identity) and agent docs on first run
            ensure_soul_md()
            ensure_agent_docs()
            # Write/merge config.yaml so hermes picks up the model
            write_config_yaml(read_env(ENV_FILE))
            self.proc = await asyncio.create_subprocess_exec(
                "hermes", "gateway", "run", "--replace",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            self.state = "running"
            self.started_at = time.time()
            asyncio.create_task(self._drain())
        except Exception as e:
            self.state = "error"
            self.logs.append(f"[error] Failed to start: {e}")

    async def stop(self):
        if not self.proc or self.proc.returncode is not None:
            self.state = "stopped"
            return
        self.state = "stopping"
        self.proc.terminate()
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            self.proc.kill()
            await self.proc.wait()
        self.state = "stopped"
        self.started_at = None

    async def restart(self):
        await self.stop()
        self.restarts += 1
        await self.start()

    async def _drain(self):
        assert self.proc and self.proc.stdout
        async for raw in self.proc.stdout:
            line = ANSI_ESCAPE.sub("", raw.decode(errors="replace").rstrip())
            self.logs.append(line)
            print(f"[gateway] {line}", flush=True)
        # Process exited — but it might have been replaced externally
        # (e.g. Hermes UI restart).  Give the replacement ~2s to bind.
        if self.state == "running":
            exit_code = self.proc.returncode
            await asyncio.sleep(2)
            if await self._is_gateway_alive():
                self.logs.append("[info] Gateway was restarted externally — still running.")
                print("[gateway] External restart detected — gateway alive on dashboard API.", flush=True)
                # Keep state as "running" but clear our proc reference
                # so start() will re-attach if the user clicks Start/Restart
                self.proc = None
            else:
                self.state = "error"
                self.logs.append(f"[error] Gateway exited (code {exit_code})")

    async def _is_gateway_alive(self) -> bool:
        """Check if a hermes gateway process is still running (possibly restarted externally).

        Strategy:
        1. Use `pgrep` to find running hermes gateway processes.
        2. Fallback: check common PID/lock file locations and verify the PID is alive.
        """
        our_pid = self.proc.pid if self.proc else None

        # Strategy 1: pgrep (most reliable on Linux/Railway)
        try:
            proc = await asyncio.create_subprocess_exec(
                "pgrep", "-f", "hermes.*gateway",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout.strip():
                # Filter out our own (now-dead) PID
                pids = [int(p) for p in stdout.decode().strip().split("\n") if p.strip()]
                alive = [p for p in pids if p != our_pid]
                if alive:
                    print(f"[gateway] pgrep found alive gateway PID(s): {alive}", flush=True)
                    return True
        except FileNotFoundError:
            pass  # pgrep not available in container

        # Strategy 2: check PID/lock files
        for pid_path in [
            Path(HERMES_HOME) / "gateway.pid",
            Path(HERMES_HOME) / "gateway.lock",
            Path("/tmp") / "hermes-gateway.pid",
        ]:
            try:
                if pid_path.exists():
                    pid = int(pid_path.read_text().strip().split("\n")[0])
                    if pid != our_pid:
                        os.kill(pid, 0)  # 0 = existence check, no signal sent
                        print(f"[gateway] PID file {pid_path} → PID {pid} alive", flush=True)
                        return True
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                continue

        return False

    def status(self) -> dict:
        uptime = int(time.time() - self.started_at) if self.started_at and self.state == "running" else None
        return {
            "state":    self.state,
            "pid":      self.proc.pid if self.proc and self.proc.returncode is None else None,
            "uptime":   uptime,
            "restarts": self.restarts,
        }


gw = Gateway()
cfg_lock = asyncio.Lock()


# ── Hermes dashboard subprocess ───────────────────────────────────────────────
class Dashboard:
    """Manages the `hermes dashboard` subprocess (native Hermes web UI).

    Bound to loopback only — we expose it to the public internet through our
    reverse proxy on $PORT, where edge basic auth guards every request.
    The dashboard is independent of the gateway: it reads config files
    directly and tolerates a stopped gateway.

    All subprocess output is streamed to our stdout (→ Railway logs) with a
    `[dashboard]` prefix AND retained in a ring buffer for diagnostics.
    Unexpected exits are explicitly logged with their return code.
    """

    def __init__(self):
        self.proc: asyncio.subprocess.Process | None = None
        self.logs: deque[str] = deque(maxlen=300)
        self._drain_task: asyncio.Task | None = None

    async def start(self):
        if self.proc and self.proc.returncode is None:
            return
        try:
            self.proc = await asyncio.create_subprocess_exec(
                "hermes", "dashboard",
                "--host", HERMES_DASHBOARD_HOST,
                "--port", str(HERMES_DASHBOARD_PORT),
                "--no-open",
                # --tui exposes /api/pty + /api/ws + /api/events so the
                # dashboard's embedded Chat tab works end-to-end. Requires
                # hermes >= v2026.4.23 — older releases exit immediately
                # with "unrecognized arguments: --tui". The Dockerfile
                # pre-builds ui-tui/dist/ so PTY spawn is instant.
                "--tui",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            print(f"[dashboard] spawned pid={self.proc.pid} → {HERMES_DASHBOARD_URL}", flush=True)
            self._drain_task = asyncio.create_task(self._drain())
        except Exception as e:
            print(f"[dashboard] FAILED to spawn: {e!r}", flush=True)

    async def _drain(self):
        """Stream subprocess output to Railway logs (prefixed) and a ring buffer."""
        assert self.proc and self.proc.stdout
        try:
            async for raw in self.proc.stdout:
                line = ANSI_ESCAPE.sub("", raw.decode(errors="replace").rstrip())
                self.logs.append(line)
                print(f"[dashboard] {line}", flush=True)
        except Exception as e:
            print(f"[dashboard] drain error: {e!r}", flush=True)
        finally:
            rc = self.proc.returncode if self.proc else None
            if rc is not None and rc != 0:
                print(f"[dashboard] EXITED with code {rc} — reverse proxy will return 503 until restart", flush=True)
            elif rc == 0:
                print(f"[dashboard] exited cleanly (code 0)", flush=True)

    async def stop(self):
        if not self.proc or self.proc.returncode is not None:
            return
        self.proc.terminate()
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            self.proc.kill()
            await self.proc.wait()


dash = Dashboard()

# Shared async HTTP client for the reverse proxy. Created lazily so we pick up
# the running event loop, torn down in lifespan.
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            follow_redirects=False,
        )
    return _http_client


# ── Route handlers ────────────────────────────────────────────────────────────
async def page_index(request: Request):
    if err := guard(request): return err
    return templates.TemplateResponse(request, "index.html")


async def route_health(request: Request):
    return JSONResponse({"status": "ok", "gateway": gw.state})


async def api_config_get(request: Request):
    if err := guard(request): return err
    async with cfg_lock:
        data = read_env(ENV_FILE)
    defs = [{"key": k, "label": l, "category": c, "secret": s} for k, l, c, s in ENV_VARS]
    return JSONResponse({"vars": mask(data), "defs": defs})


async def api_config_put(request: Request):
    if err := guard(request): return err
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    try:
        restart = body.pop("_restart", False)
        new_vars = body.get("vars", {})
        async with cfg_lock:
            existing = read_env(ENV_FILE)
            merged = unmask(new_vars, existing)
            for k, v in existing.items():
                if k not in merged:
                    merged[k] = v
            write_env(ENV_FILE, merged)
            write_config_yaml(merged)
        if restart:
            asyncio.create_task(gw.restart())
        return JSONResponse({"ok": True, "restarting": restart})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_status(request: Request):
    if err := guard(request): return err
    data = read_env(ENV_FILE)
    providers = {
        k.replace("_API_KEY","").replace("_TOKEN","").replace("HF_","HuggingFace ").replace("_"," ").title():
        {"configured": bool(data.get(k))}
        for k in PROVIDER_KEYS
    }
    channels = {
        name: {"configured": bool(v := data.get(key,"")) and v.lower() not in ("false","0","no")}
        for name, key in CHANNEL_MAP.items()
    }
    return JSONResponse({"gateway": gw.status(), "providers": providers, "channels": channels})


async def api_logs(request: Request):
    if err := guard(request): return err
    return JSONResponse({"lines": list(gw.logs)})


async def api_gw_start(request: Request):
    if err := guard(request): return err
    asyncio.create_task(gw.start())
    return JSONResponse({"ok": True})


async def api_gw_stop(request: Request):
    if err := guard(request): return err
    asyncio.create_task(gw.stop())
    return JSONResponse({"ok": True})


async def api_gw_restart(request: Request):
    if err := guard(request): return err
    asyncio.create_task(gw.restart())
    return JSONResponse({"ok": True})


async def api_config_reset(request: Request):
    if err := guard(request): return err
    asyncio.create_task(gw.stop())
    async with cfg_lock:
        if ENV_FILE.exists():
            ENV_FILE.unlink()
        write_config_yaml({})
    return JSONResponse({"ok": True})


# ── File System Editor (Brain Editor) ─────────────────────────────────────────

def resolve_path(p: str) -> Path:
    """Helper to resolve @DATA, @WORKSPACE, @PROMPTS etc."""
    if p.startswith("@PROMPTS"):
        p = p.replace("@PROMPTS", str(Path(__file__).parent / "prompts"), 1)
    elif p.startswith("@DATA"):
        p = p.replace("@DATA", str(HERMES_HOME), 1)
    elif p.startswith("@WORKSPACE"):
        p = p.replace("@WORKSPACE", str(Path(HERMES_HOME) / "workspace"), 1)
    elif p.startswith("@ROOT"):
        p = p.replace("@ROOT", "/", 1)
    
    # Prevent path traversal outside allowed areas if necessary, 
    # but for now we trust the resolved absolute path.
    return Path(p).resolve()

async def api_fs_list(request: Request):
    if err := guard(request): return err
    target_dir = request.query_params.get("dir", "@ROOT")
    
    try:
        target_path = resolve_path(target_dir)
    except Exception:
        return JSONResponse({"error": "Invalid path"}, status_code=400)
    
    if not target_path.exists() or not target_path.is_dir():
        return JSONResponse({"error": "Directory not found"}, status_code=404)
        
    items = []
    try:
        for p in target_path.iterdir():
            try:
                st = p.stat()
                items.append({
                    "name": p.name,
                    "path": str(p).replace("\\", "/"),
                    "is_dir": p.is_dir(),
                    "size": st.st_size if not p.is_dir() else 0,
                    "mtime": st.st_mtime
                })
            except Exception:
                pass
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
        
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    
    parent_dir = str(target_path.parent).replace("\\", "/")
    curr_dir = str(target_path).replace("\\", "/")
    
    return JSONResponse({
        "current_dir": curr_dir,
        "parent_dir": parent_dir if parent_dir != curr_dir else None,
        "items": items
    })

async def api_fs_read(request: Request):
    if err := guard(request): return err
    target_file = request.query_params.get("path", "")
    if not target_file:
        return JSONResponse({"error": "Path required"}, status_code=400)
        
    try:
        p = resolve_path(target_file)
        if not p.exists() or not p.is_file():
            return JSONResponse({"error": "File not found"}, status_code=404)
        content = p.read_text(encoding="utf-8")
        return JSONResponse({"content": content})
    except UnicodeDecodeError:
        return JSONResponse({"error": "Binary file cannot be read"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def api_fs_write(request: Request):
    if err := guard(request): return err
    try:
        body = await request.json()
        target_file = body.get("path")
        content = body.get("content", "")
        if not target_file: return JSONResponse({"error": "No path"}, status_code=400)
        
        p = resolve_path(target_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def api_fs_create(request: Request):
    if err := guard(request): return err
    try:
        body = await request.json()
        path = body.get("path")
        is_dir = body.get("is_dir", False)
        if not path: return JSONResponse({"error": "No path"}, status_code=400)
        
        p = resolve_path(path)
        if p.exists(): return JSONResponse({"error": "Already exists"}, status_code=400)
        p.parent.mkdir(parents=True, exist_ok=True)
        if is_dir: p.mkdir()
        else: p.touch()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def api_fs_delete(request: Request):
    if err := guard(request): return err
    try:
        body = await request.json()
        path = body.get("path")
        if not path: return JSONResponse({"error": "No path"}, status_code=400)
        
        p = resolve_path(path)
        if not p.exists(): return JSONResponse({"error": "Not found"}, status_code=404)
        import shutil
        if p.is_dir(): shutil.rmtree(p)
        else: p.unlink()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def api_fs_rename(request: Request):
    if err := guard(request): return err
    try:
        body = await request.json()
        old_path = body.get("old_path")
        new_path = body.get("new_path")
        if not old_path or not new_path: return JSONResponse({"error": "Paths required"}, status_code=400)
        p_old = resolve_path(old_path)
        p_new = resolve_path(new_path)
        if not p_old.exists(): return JSONResponse({"error": "Source not found"}, status_code=404)
        if p_new.exists(): return JSONResponse({"error": "Destination exists"}, status_code=400)
        p_new.parent.mkdir(parents=True, exist_ok=True)
        p_old.rename(p_new)
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

async def api_fs_media(request: Request):
    if err := guard(request): return err
    target_file = request.query_params.get("path", "")
    if not target_file:
        return JSONResponse({"error": "Path required"}, status_code=400)
        
    p = resolve_path(target_file)
    if not p.exists() or not p.is_file():
        return JSONResponse({"error": "File not found"}, status_code=404)
        
    return FileResponse(p)


# ── Pairing ───────────────────────────────────────────────────────────────────
def _pjson(path: Path) -> dict:
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        return {}


def _wjson(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    try: os.chmod(path, 0o600)
    except OSError: pass


def _platforms(suffix: str) -> list[str]:
    if not PAIRING_DIR.exists(): return []
    return [f.stem.rsplit(f"-{suffix}", 1)[0] for f in PAIRING_DIR.glob(f"*-{suffix}.json")]


async def api_pairing_pending(request: Request):
    if err := guard(request): return err
    now = time.time()
    out = []
    for p in _platforms("pending"):
        for code, info in _pjson(PAIRING_DIR / f"{p}-pending.json").items():
            if now - info.get("created_at", now) <= PAIRING_TTL:
                out.append({"platform": p, "code": code,
                            "user_id": info.get("user_id",""), "user_name": info.get("user_name",""),
                            "age_minutes": int((now - info.get("created_at", now)) / 60)})
    return JSONResponse({"pending": out})


async def api_pairing_approve(request: Request):
    if err := guard(request): return err
    try: body = await request.json()
    except Exception: return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    platform, code = body.get("platform",""), body.get("code","").upper().strip()
    if not platform or not code:
        return JSONResponse({"error": "platform and code required"}, status_code=400)
    pending_path = PAIRING_DIR / f"{platform}-pending.json"
    pending = _pjson(pending_path)
    if code not in pending:
        return JSONResponse({"error": "Code not found"}, status_code=404)
    entry = pending.pop(code)
    _wjson(pending_path, pending)
    approved = _pjson(PAIRING_DIR / f"{platform}-approved.json")
    approved[entry["user_id"]] = {"user_name": entry.get("user_name",""), "approved_at": time.time()}
    _wjson(PAIRING_DIR / f"{platform}-approved.json", approved)
    return JSONResponse({"ok": True})


async def api_pairing_deny(request: Request):
    if err := guard(request): return err
    try: body = await request.json()
    except Exception: return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    platform, code = body.get("platform",""), body.get("code","").upper().strip()
    p = PAIRING_DIR / f"{platform}-pending.json"
    pending = _pjson(p)
    if code in pending:
        del pending[code]
        _wjson(p, pending)
    return JSONResponse({"ok": True})


async def api_pairing_approved(request: Request):
    if err := guard(request): return err
    out = []
    for p in _platforms("approved"):
        for uid, info in _pjson(PAIRING_DIR / f"{p}-approved.json").items():
            out.append({"platform": p, "user_id": uid,
                        "user_name": info.get("user_name",""), "approved_at": info.get("approved_at",0)})
    return JSONResponse({"approved": out})


async def api_pairing_revoke(request: Request):
    if err := guard(request): return err
    try: body = await request.json()
    except Exception: return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    platform, uid = body.get("platform",""), body.get("user_id","")
    if not platform or not uid:
        return JSONResponse({"error": "platform and user_id required"}, status_code=400)
    p = PAIRING_DIR / f"{platform}-approved.json"
    approved = _pjson(p)
    if uid in approved:
        del approved[uid]
        _wjson(p, approved)
    return JSONResponse({"ok": True})


# ── Reverse proxy → Hermes dashboard ──────────────────────────────────────────
_WIDGET_LINK_STYLE = (
    "background:rgba(20,24,31,0.92);backdrop-filter:blur(8px);"
    "border:1px solid #252d3d;border-radius:6px;padding:6px 12px;"
    "color:#c9d1d9;text-decoration:none;display:inline-flex;"
    "align-items:center;gap:6px;"
)
BACK_TO_SETUP_WIDGET = (
    '<div id="hermes-back-widget" style="position:fixed;bottom:14px;right:14px;'
    'z-index:99999;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;'
    'font-size:11px;display:flex;gap:8px;">'
    f'<a href="/setup" style="{_WIDGET_LINK_STYLE}">← Setup</a>'
    f'<a href="/logout" style="{_WIDGET_LINK_STYLE}">Sign out</a>'
    '</div>'
)

DASHBOARD_UNAVAILABLE_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Dashboard starting…</title>
<style>body{background:#0d0f14;color:#c9d1d9;font-family:ui-monospace,Menlo,monospace;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.card{max-width:480px;padding:32px;border:1px solid #252d3d;border-radius:12px;
background:#14181f;text-align:center}
h1{font-size:16px;color:#d29922;margin:0 0 12px;font-weight:600}
p{font-size:13px;color:#6b7688;line-height:1.6;margin:0 0 16px}
a{color:#6272ff;text-decoration:none;border:1px solid #252d3d;border-radius:6px;
padding:7px 14px;font-size:12px;display:inline-block}
a:hover{border-color:#6272ff}</style></head>
<body><div class="card">
<h1>⚠ Hermes dashboard unavailable</h1>
<p>The native Hermes dashboard is not responding on port %d.<br>
It may still be starting up, or it may have crashed.</p>
<p>Try refreshing in a few seconds, or head back to setup.</p>
<a href="/setup">← Back to Setup</a>
</div>
<script>setTimeout(()=>location.reload(),4000);</script>
</body></html>""" % HERMES_DASHBOARD_PORT


async def _proxy_to_dashboard(request: Request) -> Response:
    """Forward an authenticated request to the Hermes dashboard subprocess.

    Assumes edge auth (basic auth middleware) has already validated the caller.
    HTTP-only: the native Hermes dashboard does not use WebSockets.
    """
    client = get_http_client()
    target = f"{HERMES_DASHBOARD_URL}{request.url.path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    req_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in HOP_BY_HOP
    }
    body = await request.body()

    try:
        upstream = await client.request(
            request.method,
            target,
            headers=req_headers,
            content=body,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return HTMLResponse(DASHBOARD_UNAVAILABLE_HTML, status_code=503)
    except httpx.RequestError as e:
        print(f"[proxy] upstream error for {request.method} {request.url.path}: {e}", flush=True)
        return HTMLResponse(DASHBOARD_UNAVAILABLE_HTML, status_code=502)

    # Surface non-2xx responses from hermes into Railway logs so we can
    # diagnose 401/500s without needing browser DevTools access.
    if upstream.status_code >= 400:
        body_snip = upstream.content[:200].decode("utf-8", errors="replace")
        print(
            f"[proxy] {request.method} {request.url.path} -> {upstream.status_code} "
            f"body={body_snip!r}",
            flush=True,
        )

    # Strip hop-by-hop and length/encoding headers — Starlette recomputes them.
    resp_headers = {
        k: v for k, v in upstream.headers.items()
        if k.lower() not in HOP_BY_HOP
        and k.lower() not in ("content-encoding", "content-length")
    }

    content = upstream.content
    content_type = upstream.headers.get("content-type", "").lower()

    # Inject the "← Setup" widget into HTML pages so users can always return.
    if "text/html" in content_type and b"</body>" in content:
        try:
            text = content.decode("utf-8", errors="replace")
            text = text.replace("</body>", BACK_TO_SETUP_WIDGET + "</body>", 1)
            content = text.encode("utf-8")
        except Exception:
            pass  # on any error, fall back to raw upstream content

    return Response(
        content=content,
        status_code=upstream.status_code,
        headers=resp_headers,
    )


async def route_root(request: Request) -> Response:
    """GET /: first-visit smart redirect, otherwise proxy to the dashboard.

    - Unconfigured + bare GET `/` → bounce to `/setup` so new users land on
      the wizard instead of a half-empty dashboard.
    - Sidebar / in-app links pass `?force=1` to opt out of that redirect —
      users who explicitly want the dashboard (e.g. to set providers via
      the Keys tab) can still reach it without saving config first.
    - Non-GET (SPA API calls, etc.) always proxy through.
    """
    if err := guard(request): return err
    if (request.method == "GET"
            and request.query_params.get("force") != "1"
            and not is_config_complete()):
        return RedirectResponse("/setup", status_code=302)
    return await _proxy_to_dashboard(request)


async def route_proxy(request: Request) -> Response:
    """Catch-all: forward any unmatched path to the Hermes dashboard."""
    if err := guard(request): return err
    return await _proxy_to_dashboard(request)


async def route_setup_404(request: Request) -> Response:
    """Typos under /setup/* should 404 here — not fall through to the proxy."""
    if err := guard(request): return err
    return Response("Not Found", status_code=404, media_type="text/plain")


# ── App lifecycle ─────────────────────────────────────────────────────────────
async def auto_start():
    if is_config_complete():
        asyncio.create_task(gw.start())
    else:
        print("[server] Config incomplete — gateway not started. Configure provider + model in the admin UI.", flush=True)


@asynccontextmanager
async def lifespan(app):
    # Dashboard runs always — it's the user-facing UI after setup is done,
    # and it's independent of gateway state.
    asyncio.create_task(dash.start())
    await auto_start()
    # Seed infrastructure manifest if missing in persistent storage
    try:
        infra_dir = Path(HERMES_HOME) / "docs"
        infra_dir.mkdir(parents=True, exist_ok=True)
        infra_file = infra_dir / "INFRA_MANIFEST.md"
        if not infra_file.exists():
            # In Railway, the repo content is at /app/
            template = Path("/app/docs/INFRA_MANIFEST.md")
            if not template.exists():
                # Fallback for local dev or other environments
                template = Path(__file__).parent / "docs" / "INFRA_MANIFEST.md"
            
            if template.exists():
                print(f"[server] Seeding manifest from {template} to {infra_file}", flush=True)
                import shutil
                shutil.copy(template, infra_file)
            else:
                print(f"[server] WARNING: Template manifest not found at {template}", flush=True)
    except Exception as e:
        print(f"[server] Error seeding manifest: {e}", flush=True)

    try:
        yield
    finally:
        await asyncio.gather(
            gw.stop(),
            dash.stop(),
            return_exceptions=True,
        )
        global _http_client
        if _http_client is not None:
            await _http_client.aclose()
            _http_client = None


# ── WebSocket reverse proxy ──────────────────────────────────────────────────
# The hermes dashboard exposes 4 WebSocket endpoints when started with --tui.
# Three are opened by the browser SPA and need to flow through our reverse
# proxy; the fourth (/api/pub) is opened only by the PTY child against
# loopback and is intentionally NOT proxied — exposing it would let an
# authed user spam events into channels.
#
#   /api/pty     binary stream — embedded TUI keystrokes/output
#   /api/ws      JSON-RPC      — gateway sidecar driving Chat metadata
#   /api/events  text frames   — dashboard subscriber for /api/pub fan-out
#
# Auth model (matches the HTTP proxy):
#   * Edge: our HMAC cookie via _is_authenticated. WebSocket inherits .cookies
#     from starlette HTTPConnection so the same helper works unchanged.
#   * Upstream: hermes's own ?token=<_SESSION_TOKEN> query param. The SPA
#     fetches that token via /api/auth/session-token and includes it in the
#     WS URL, so we just forward path + query verbatim.
PROXIED_WS_PATHS = ("/api/pty", "/api/ws", "/api/events")


async def _ws_pump_client_to_upstream(
    client: WebSocket,
    upstream: websockets.WebSocketClientProtocol,
) -> None:
    """Forward client → upstream until the client side disconnects.

    Handles both binary (PTY bytes) and text (JSON-RPC) frames.
    """
    try:
        while True:
            msg = await client.receive()
            if msg.get("type") == "websocket.disconnect":
                return
            data = msg.get("bytes")
            if data is not None:
                await upstream.send(data)
                continue
            text = msg.get("text")
            if text is not None:
                await upstream.send(text)
    except (WebSocketDisconnect, websockets.exceptions.ConnectionClosed):
        return
    except Exception as e:
        print(f"[ws-proxy] client→upstream error on {client.url.path}: {e!r}", flush=True)
        return


async def _ws_pump_upstream_to_client(
    upstream: websockets.WebSocketClientProtocol,
    client: WebSocket,
) -> None:
    """Forward upstream → client until upstream closes."""
    try:
        async for msg in upstream:
            if isinstance(msg, bytes):
                await client.send_bytes(msg)
            else:
                await client.send_text(msg)
    except (websockets.exceptions.ConnectionClosed, WebSocketDisconnect):
        return
    except Exception as e:
        print(f"[ws-proxy] upstream→client error on {client.url.path}: {e!r}", flush=True)
        return


async def ws_proxy(websocket: WebSocket) -> None:
    """Reverse-proxy a single WebSocket from browser → hermes dashboard.

    Order matters: connect upstream BEFORE accepting the client. If hermes
    is wedged or rejects the upgrade, we close the client with a meaningful
    code instead of accepting and then dropping silently.

    Connection lifecycle:
      1. Verify edge cookie auth → 4401 close on failure
      2. Open upstream WS with bounded open_timeout → 1011 on failure
      3. Accept client
      4. Spawn two pump tasks (bidirectional byte forwarding)
      5. When either direction ends (client navigates away, upstream PTY
         exits, etc.), cancel the other task and close both sockets
    """
    # 1. Edge auth.
    if not _is_authenticated(websocket):
        # Close before accept — browser sees the handshake fail (expected
        # for unauthenticated calls).
        await websocket.close(code=4401)
        return

    # 2. Build upstream URL preserving the SPA's path + query (the query
    #    contains the hermes session token + channel id).
    path = websocket.url.path
    qs = websocket.url.query
    upstream_url = f"ws://{HERMES_DASHBOARD_HOST}:{HERMES_DASHBOARD_PORT}{path}"
    if qs:
        upstream_url = f"{upstream_url}?{qs}"

    try:
        upstream = await websockets.connect(
            upstream_url,
            open_timeout=5,
            # Don't forward client cookies/headers — hermes WS auth is
            # purely token-based via the URL, and forwarding random
            # headers risks future upstream surprises.
        )
    except (asyncio.TimeoutError, OSError, websockets.exceptions.WebSocketException) as e:
        # Hermes dashboard down, restarting, or rejected the upgrade
        # (e.g. bad/missing session token).
        print(f"[ws-proxy] upstream connect failed for {path}: {e!r}", flush=True)
        # 1011 = internal error; client SPA will surface a generic close.
        await websocket.close(code=1011)
        return

    # 3. Both sides ready — accept and start pumping.
    await websocket.accept()

    pump_in = asyncio.create_task(_ws_pump_client_to_upstream(websocket, upstream))
    pump_out = asyncio.create_task(_ws_pump_upstream_to_client(upstream, websocket))

    try:
        # First side to finish wins; cancel the other.
        done, pending = await asyncio.wait(
            (pump_in, pump_out),
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
    finally:
        # websockets.connect() outside `async with` doesn't auto-close;
        # do it explicitly. Same for the client side if still open.
        try:
            await upstream.close()
        except Exception:
            pass
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass



# ── Version Management ────────────────────────────────────────────────────────
def get_current_hermes_version():
    """Parses Dockerfile to find the current HERMES_REF."""
    try:
        # Check environment first
        if os.environ.get("HERMES_REF"):
            return os.environ.get("HERMES_REF")
            
        # Try multiple locations and be extremely lenient
        cwd = os.getcwd()
        possible_paths = [
            os.path.join(cwd, "Dockerfile"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "Dockerfile"),
            "/app/Dockerfile",
            "/workspace/Dockerfile"
        ]
        
        for p in possible_paths:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "HERMES_REF=" in line and not line.strip().startswith("#"):
                            return line.split("=")[-1].strip()
                            
        return "v2026.4.30" # Fallback to known template version if detection fails
    except Exception:
        return "unknown"

async def get_latest_hermes_release():
    """Fetches the latest release info from GitHub."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            print("[server] Checking for updates from GitHub...", flush=True)
            resp = await client.get("https://api.github.com/repos/NousResearch/hermes-agent/releases/latest")
            if resp.status_code == 200:
                data = resp.json()
                v = data.get("tag_name", "unknown")
                print(f"[server] Latest upstream version: {v}", flush=True)
                return {
                    "tag": v,
                    "name": data.get("name", ""),
                    "body": data.get("body", ""),
                    "url": data.get("html_url", "")
                }
            else:
                print(f"[server] GitHub API returned status {resp.status_code}", flush=True)
    except Exception as e:
        print(f"[server] Version check failed: {e}", flush=True)
    return None

# Version Tag to Name Mapping
VERSION_MAP = {
    "v2026.5.7": "Hermes Agent v0.13.0",
    "v2026.4.30": "Hermes Agent v0.12.0",
    "v2026.4.15": "Hermes Agent v0.11.0"
}

async def api_version_status(request: Request):
    if err := guard(request): return err
    current = get_current_hermes_version()
    latest = await get_latest_hermes_release()
    
    # Try to get user-friendly names
    c_name = VERSION_MAP.get(current, f"Hermes Agent ({current})")
    l_tag = latest["tag"] if latest else "unknown"
    l_name = latest["name"] if latest else ""
    if not l_name:
        l_name = VERSION_MAP.get(l_tag, f"Hermes Agent ({l_tag})")
        
    return JSONResponse({
        "current": current,
        "current_name": c_name,
        "latest": l_tag,
        "name": l_name,
        "changelog": latest["body"] if latest else "",
        "url": latest["url"] if latest else ""
    })

async def api_version_analyze(request: Request):
    if err := guard(request): return err
    data = await request.json()
    changelog = data.get("changelog", "")
    
    risks = []
    highlights = []
    c = changelog.lower()
    
    # 1. Analyze Risks
    if "breaking" in c:
        risks.append({"level": "önemli", "icon": "🔴", "text": "KRİTİK: Geriye dönük uyumsuz değişiklikler.", "action": "MCP bağlantılarını kontrol et."})
    if "mcp" in c or "tool" in c:
        risks.append({"level": "uyari", "icon": "🟠", "text": "Araç/MCP Protokol Güncellemesi.", "action": "Token kullanımını gözlemleyin."})
    
    # 2. Extract Catchy Highlights
    # Define catchy mappings
    mappings = {
        "video": "🎥 Native Video Understanding (Gemini & Multimodal)",
        "voice": "🎙️ AI Voice Cloning & TTS Custom Providers",
        "plugins": "🔌 Advanced Plugin Management & Profiles",
        "routing": "🛣️ Intelligent Skill Media Routing",
        "lifecycle": "🔄 New LLM Output Lifecycle Hooks",
        "theme": "🎨 UI/UX Improvements & New Themes"
    }
    
    found_keys = set()
    for key, catchy in mappings.items():
        if key in c:
            highlights.append(catchy)
            found_keys.add(key)
            if len(highlights) >= 4: break

    if not highlights:
        highlights = ["✨ Genel performans iyileştirmeleri ve stabilite yamaları."]

    return JSONResponse({
        "summary": "AI Sürüm Analizi Tamamlandı.",
        "risks": risks,
        "highlights": highlights,
        "manifest_path": "@DATA/docs/INFRA_MANIFEST.md"
    })

async def api_version_upgrade(request: Request):
    if err := guard(request): return err
    data = await request.json()
    new_version = data.get("version")
    if not new_version:
        return JSONResponse({"error": "No version specified"}, status_code=400)
    
    try:
        dockerfile_path = Path(__file__).parent / "Dockerfile"
        content = dockerfile_path.read_text(encoding="utf-8")
        
        # Non-destructive update of the version arg
        new_content = re.sub(
            r"ARG HERMES_REF=(v\d+\.\d+\.\d+|main)", 
            f"ARG HERMES_REF={new_version}", 
            content
        )
        # 1. Update local file (so user can see it via SSH/Editor)
        dockerfile_path.write_text(new_content, encoding="utf-8")
        
        # 2. Gold Standard: Push change to GitHub via API to trigger redeploy
        owner = os.environ.get("RAILWAY_GIT_REPO_OWNER")
        repo = os.environ.get("RAILWAY_GIT_REPO_NAME")
        
        # Load config from .env file
        app_config = read_env(ENV_FILE)
        token = app_config.get("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
        
        gh_message = ""
        if owner and repo and token:
            try:
                import base64
                async with httpx.AsyncClient() as client:
                    # Get the current file SHA from GitHub
                    url = f"https://api.github.com/repos/{owner}/{repo}/contents/Dockerfile"
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github.v3+json",
                        "User-Agent": "Hermes-Railway-Admin"
                    }
                    r = await client.get(url, headers=headers)
                    if r.status_code == 200:
                        file_data = r.json()
                        sha = file_data.get("sha")
                        
                        # Commit the change
                        payload = {
                            "message": f"chore: upgrade hermes to {new_version} (auto-patch)",
                            "content": base64.b64encode(new_content.encode("utf-8")).decode("utf-8"),
                            "sha": sha,
                            "branch": os.environ.get("RAILWAY_GIT_BRANCH", "main")
                        }
                        r2 = await client.put(url, headers=headers, json=payload)
                        if r2.status_code in (200, 201):
                            gh_message = " Değişiklik GitHub'a push edildi, yeni deployment otomatik başlıyor! 🚀"
                        else:
                            gh_message = f" GitHub API hatası: {r2.status_code}"
            except Exception as e:
                gh_message = f" GitHub push başarısız: {str(e)}"
        else:
            gh_message = " GITHUB_TOKEN eksik, değişiklik sadece yerel yapıldı. Lütfen manuel push yapın."

        return JSONResponse({
            "success": True, 
            "message": f"Dockerfile {new_version} sürümüne güncellendi.{gh_message}"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


ANY_METHOD = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]


routes = [
    # Public — no auth required.
    Route("/health",                            route_health),
    Route("/login",                             page_login,          methods=["GET"]),
    Route("/login",                             login_post,          methods=["POST"]),
    Route("/logout",                            logout),

    # Our setup wizard + management API, all under /setup/* (cookie-auth guarded).
    Route("/setup",                             page_index),
    Route("/setup/",                            page_index),
    Route("/setup/api/config",                  api_config_get,      methods=["GET"]),
    Route("/setup/api/config",                  api_config_put,      methods=["PUT"]),
    Route("/setup/api/status",                  api_status),
    Route("/setup/api/logs",                    api_logs),
    Route("/setup/api/gateway/start",           api_gw_start,        methods=["POST"]),
    Route("/setup/api/gateway/stop",            api_gw_stop,         methods=["POST"]),
    Route("/setup/api/gateway/restart",         api_gw_restart,      methods=["POST"]),
    Route("/setup/api/config/reset",            api_config_reset,    methods=["POST"]),
    Route("/setup/api/fs/list",                 api_fs_list),
    Route("/setup/api/fs/read",                 api_fs_read),
    Route("/setup/api/fs/write",                api_fs_write,        methods=["POST"]),
    Route("/setup/api/fs/create",               api_fs_create,       methods=["POST"]),
    Route("/setup/api/fs/delete",               api_fs_delete,       methods=["POST"]),
    Route("/setup/api/fs/rename",               api_fs_rename,       methods=["POST"]),
    Route("/setup/api/fs/media",                api_fs_media),
    Route("/setup/api/pairing/pending",         api_pairing_pending),
    Route("/setup/api/pairing/approve",         api_pairing_approve, methods=["POST"]),
    Route("/setup/api/pairing/deny",            api_pairing_deny,    methods=["POST"]),
    Route("/setup/api/pairing/approved",        api_pairing_approved),
    Route("/setup/api/pairing/revoke",          api_pairing_revoke,  methods=["POST"]),
    Route("/setup/api/version/status",           api_version_status),
    Route("/setup/api/version/analyze",          api_version_analyze, methods=["POST"]),
    Route("/setup/api/version/upgrade",          api_version_upgrade, methods=["POST"]),

    # /setup/* typos return a real 404 — not a silent proxy fallthrough.
    Route("/setup/{path:path}",                 route_setup_404,     methods=ANY_METHOD),

    # Reverse-proxy hermes's dashboard WebSockets (Chat tab + sidecar).
    # WebSocketRoute is matched independently of HTTP routes, so order
    # relative to the catch-all HTTP `Route("/{path:path}", ...)` below
    # doesn't matter — but listing them as a group keeps the surface
    # area auditable. Only paths in PROXIED_WS_PATHS are forwarded;
    # /api/pub is intentionally omitted.
    WebSocketRoute("/api/pty",                  ws_proxy),
    WebSocketRoute("/api/ws",                   ws_proxy),
    WebSocketRoute("/api/events",               ws_proxy),

    # Root: redirect to /setup if unconfigured, otherwise proxy the dashboard.
    Route("/",                                  route_root,          methods=ANY_METHOD),

    # Catch-all: everything else proxies to the Hermes dashboard subprocess.
    Route("/{path:path}",                       route_proxy,         methods=ANY_METHOD),
]

# No middleware — auth is enforced per-handler via guard(). This keeps /health
# and /login truly unauthenticated without middleware gymnastics.
app = Starlette(routes=routes, lifespan=lifespan)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info", loop="asyncio")
    server = uvicorn.Server(config)

    def _shutdown():
        loop.create_task(gw.stop())
        loop.create_task(dash.stop())
        server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _shutdown)

    loop.run_until_complete(server.serve())
