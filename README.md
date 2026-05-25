# Hermes Agent — Ultimate Autonomous PKB (Token Plan Max Optimized)

Deploy [Hermes Agent](https://github.com/NousResearch/hermes-agent) on [Railway](https://railway.app) with full support for **MiniMax Token Plan Max (Global)**, **Event-Driven RAG (Webhook)**, and **Agent Portability (.cursorrules)**. 

This repository goes beyond a simple fork; it is a meticulously engineered, premium foundation for developing fully autonomous, self-aware AI agents connected directly to your Personal Knowledge Base (PKB) like Obsidian.

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template?template=https://github.com/algorytma/hermes-minimax-railway-template&referralCode=QXdhdr)

---

## 🚀 The Three Pillars of This Architecture

### 1. 🧠 Event-Driven Webhook RAG (Knowledge Base Integration)
Forget slow polling mechanisms. We've introduced a hyper-efficient, 2-Way Git Sync architecture.
- **Instant Triggers:** When you update a note in your Obsidian vault and push to GitHub, a webhook instantly pings `/api/webhook/github`.
- **Zero Conflict Flow:** The server executes an asynchronous `git pull --rebase`, indexes your new markdown files into the **Vector DB**, and updates the AI's "Brain".
- **Infinite Loop Guard:** When Hermes Agent writes metadata or thoughts back to your notes, the webhook smartly ignores "Agent Commits" to prevent infinite trigger loops.

### 2. 🦾 Official MiniMax Native MCP Integration
We have transitioned from custom forks to the official **MiniMax MCP Ecosystem**.
- **Media Engine:** Powered by `minimax-mcp` for flawless HD Video (Hailuo-2.3), Text-to-Speech (2.8), and Image generation.
- **Research Engine:** Powered by `minimax-coding-plan-mcp` for lightning-fast Web Search and VLM.
- **Global API Optimized:** Bypasses default constraints by pointing natively to `api.minimax.io`.

### 3. 🛸 True Agent Portability & Autonomy
Developed strictly under **"AI Agent Workflow Portability"** rules. 
- **`.cursorrules` Driven:** Whether you open this repo in Cursor, Windsurf, or inject a brand-new AI Agent (like Gemini Antigravity), the agent instantly reads `.cursorrules` and understands the entire deployment, coding, and logging logic.
- **Environment Modularity:** Strict separation between Developer (Root `.env`) and User (Persistent Storage `/.hermes/data/.env`) configurations.

---

## 🏗️ System Architecture

```mermaid
graph TD
    %% User and Local Interactions
    User[👤 You (Obsidian / Local)] -->|Write Notes| LocalGit[Local Git Repo]
    LocalGit -->|Git Push| GitHub[🐙 Private GitHub Repo]
    
    %% Webhook and Server Flow
    GitHub -->|Webhook Trigger| FastAPI[⚡ Hermes Server (FastAPI)]
    
    subgraph Railway Production Container
        FastAPI -->|Async Task: perform_rag_sync| GitPull[Git Pull --rebase]
        GitPull --> RAG[🧠 RAG Indexing & Vector DB]
        RAG --> LLM[🤖 MiniMax LLM & MCP Servers]
        LLM -->|Inject Metadata/Thoughts| GitPush[Git Push origin main]
    end
    
    %% Closing the loop
    GitPush -->|Agent Commits| GitHub
    GitHub -.->|Infinite Loop Guard| FastAPI
```

---

## 🛠️ Getting Started (End Users)

### 1. Get your API Keys
- **MiniMax:** Go to [MiniMax AI Studio](https://platform.minimax.io/), and copy your Token Plan Max API key (starts with `sk-cp-`).
- **GitHub PAT:** Generate a Fine-Grained Personal Access Token with **Contents: Read and Write** permissions.

### 2. Deploy to Railway
1. Click the **Deploy on Railway** button above.
2. Set your `ADMIN_PASSWORD`.
3. Ensure a **Volume** is mounted at `/data`.

### 3. Setup (WebUI)
1. Open your Railway app URL and login with `admin` and your password.
2. In the **Setup Dashboard**:
   - Check **"Enable MiniMax Token Plan (Global)"**.
   - Input your GitHub Webhook Secret and Repository URL.
3. Your configurations are saved persistently in `/.hermes/data/.env`.

---

## 👩‍💻 Developer Guidelines (Contributing)

If you are a human developer or an AI Agent, please adhere to our strict `.cursorrules`:
1. **Never commit the root `.env` file.**
2. Use **Terminal (`git push`)** for large file modifications (like `server.py`). Only use MCP tools for small markdown adjustments.
3. Read `docs/INFRA_MANIFEST.md` before attempting any architectural changes.

See our [CONTRIBUTING.md](./CONTRIBUTING.md) for more details.

---

## 📜 Credits & Recognition

- **Original Project:** [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
- **Base UI Template:** [praveen-ks-2001/hermes-agent-template](https://github.com/praveen-ks-2001/hermes-agent-template)
- **Architectural Overhaul:** Developed with ❤️ by **algorytma** for the AI Community.
