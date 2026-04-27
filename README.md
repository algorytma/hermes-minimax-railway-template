# Hermes Agent — MiniMax Token Plan Max Optimized

Deploy [Hermes Agent](https://github.com/NousResearch/hermes-agent) on [Railway](https://railway.app) with full support for **MiniMax Token Plan Max** (Global). This fork fixes critical API host issues and integrates high-performance MCP servers for Research and Media generation.

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template?template=https://github.com/algorytma/hermes-minimax-railway-template&referralCode=QXdhdr)

## 🚀 Why this Fork?

Standard Hermes Agent templates often struggle with the **MiniMax Global API** (Token Plan Max) because:
1. **API Host Mismatch:** Default templates use `api.minimax.chat` (Mainland China), which fails for Global accounts. This fork defaults to `api.minimax.io`.
2. **Missing Multimodal Tools:** Video, Music, and advanced TTS require specific MCP configurations.
3. **Complex Setup:** Manually editing `config.yaml` on Railway is tedious.

**Our Solution:** A premium setup UI with a single-click "Token Plan" toggle that injects optimized MCP configurations for both **Research** and **Media**.

# 🚀 Hermes MiniMax — Native Architecture Upgrade

This repository has been upgraded to the **Official MiniMax Native Architecture**. We have transitioned from custom forks and community patches to the official **MiniMax MCP Ecosystem**, ensuring the highest level of stability, speed, and multimodal compatibility.

## 🌟 Key Features of the Native Upgrade
- **Official Media Engine:** Powered by `uvx minimax-mcp` for flawless Text-to-Speech, Image, and Video generation.
- **Official Research Engine:** Powered by `minimax-coding-plan-mcp` for lightning-fast Web Search and VLM.
- **Auto-Model Selection:** No more manual model names. The official MCP servers automatically use the best models supported by your **Token Plan Max**.
- **Enhanced Stability:** Direct integration with MiniMax Global API endpoints, bypassing complex routing layers.

## 🛠 Technical Stack
- **Core:** Hermes Agent (Python)
- **Official MCPs:**
  - `minimax-mcp` (Media: Video, Audio, Image)
  - `minimax-coding-plan-mcp` (Research: Search, Vision)
- **Deployment:** Railway (Dockerized)
- **Persistence:** Mounted `/data` volume for configuration and media storage.

## ✨ Features

- **MiniMax Token Plan Max Optimized** — One-click activation of Video, Music, TTS, and Search tools.
- **Dual MCP Integration:**
  - **Research MCP:** High-speed web search and image understanding.
  - **Media MCP:** Powered by `algorytma/MiniMax-MCP-JS` for high-quality video (Hailuo-2.3), music (2.6), and HD speech (2.8).
- **Admin Dashboard** — Sleek dark-themed UI for gateway management and user pairing.
- **One-Page Setup** — No config files to edit.
- **Railway Ready** — Persistent configuration via `/data` volume.

## 🛠️ Getting Started

### 1. Get your MiniMax API Key
1. Go to [MiniMax AI Studio](https://platform.minimax.io/).
2. Copy your **Token Plan Max** API key (starts with `sk-cp-`).

### 2. Deploy to Railway
1. Click the **Deploy on Railway** button above.
2. Set your `ADMIN_PASSWORD`.
3. Ensure a **Volume** is mounted at `/data`.

### 3. Configure MiniMax
1. Open your Railway app URL.
2. Login with `admin` and your password.
3. In the **LLM Provider** section:
   - Select **MiniMax**.
   - Paste your API key.
   - Enter your model (e.g., `minimax/MiniMax-M2.7`).
   - **CRITICAL:** Check the box **"Enable MiniMax Token Plan (Global)"**.
4. Configure a Messaging Channel (e.g., Telegram).
5. Click **Save & Start**.

## 🎨 Supported Tools (MiniMax Token Plan)

| Feature | Model | Description |
|---------|-------|-------------|
| **Search** | `coding-plan` | Real-time web search and coding research. |
| **Video** | `Hailuo-2.3` | High-quality cinematic video generation. |
| **Music** | `music-2.6` | AI-generated music with lyrics. |
| **Speech** | `speech-2.8-hd` | Ultra-realistic text-to-speech. |
| **Image** | `image-01` | High-fidelity image generation. |

## 🏗️ Architecture

```
Railway Container
├── Python Admin Server (Starlette + Uvicorn)
│   ├── /setup       — Premium Setup UI
│   └── /api/*       — Gateway orchestration
└── hermes gateway   — Async subprocess
    ├── minimax-research (uvx)
    └── minimax-media (npx)
```

## 📜 Credits

- **Original Project:** [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
- **Base UI Template:** [praveen-ks-2001/hermes-agent-template](https://github.com/praveen-ks-2001/hermes-agent-template)
- **MiniMax MCP Fork:** [algorytma/MiniMax-MCP-JS](https://github.com/algorytma/MiniMax-MCP-JS)

---
Developed with ❤️ by **algorytma** for the AI Community.
