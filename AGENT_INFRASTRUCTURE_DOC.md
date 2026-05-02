# HERMES: INFRASTRUCTURE & ARCHITECTURE DOCUMENTATION (v1.4)

## 1. Introduction
This document serves as the self-awareness and architectural blueprint for the Hermes autonomous agent. It outlines the historical context, the challenges faced with official integrations, and the current Hybrid MCP (Model Context Protocol) architecture running on Railway.

## 2. History & The "Token Plan" Crisis
Initially, this project utilized the official Python-based `minimax-mcp` server for all capabilities. However, a critical architectural blocker emerged:
- **The 2061 Error:** When attempting to generate multimedia (Audio, Video, Music), the API returned `Error 2061: Your current token plan not support model`.
- **Root Cause:** Analysis of the official Python MCP source code revealed that legacy models (e.g., `music-2.0`, `speech-02-hd`) were **hardcoded** into the tools. As the current account holds a premium **Token Plan Max** (which requires modern models like `speech-2.8-hd` and `music-2.6`), the API rejected the requests. The official Python tools lacked the flexibility to accept dynamic model parameters.

## 3. The Hybrid "Highway" Solution
To bypass the hardcoded limitations of the official package without losing functionality, a **Hybrid MCP Architecture** was deployed:

1. **Research Node (Official Python):** 
   - Uses `uvx minimax-coding-plan-mcp`.
   - Maintained for Web Search and Vision/VLM (Image Understanding) as these tools work flawlessly without model parameter conflicts.
   
2. **Media Node (Custom JS Fork):** 
   - Uses `npx -y algorytma/MiniMax-MCP-JS`.
   - The media processing was transitioned to a highly flexible, custom JavaScript fork. This fork stripped away rigid `enum` validations and enabled the agent to dynamically pass any `model` string to the API.
   - **Local Storage Bypass:** To prevent the 5-minute URL expiry issue inherent to the MiniMax API, the JS server is configured with `MINIMAX_MCP_BASE_PATH: "/data/.hermes/mcp-output"`. All generated media is instantly downloaded to local storage, providing the agent with absolute file paths.

## 4. Token Plan Max: Authorized Models
As the agent, you operate under a premium "Token Plan Max". To ensure the API accepts your requests, you **MUST ALWAYS** explicitly pass the following model names to the Media MCP tools. Never rely on the tool's default models:

- **Text-to-Speech (TTS):** `speech-2.8-hd` (Fallback: `speech-01`)
- **Video Generation:** `Hailuo-2.3-Fast-768P-6s` (Fallback: `Hailuo-2.3-768P-6s` or `video-01`)
- **Music Generation:** `music-2.6` (Fallback: `music-2.5`)
- **Lyrics Generation:** `lyrics_generation`
- **Music Cover:** `music-cover`
- **Image Generation:** `image-01`

## 5. Daily Quotas & Resource Planning
You operate under strict daily API limits. It is **critical** to plan your media generation requests efficiently and avoid unnecessary calls (e.g., do not generate 3 videos or music tracks if the user only asked for 1). Be highly aware of your daily quotas to prevent "quota exceeded" errors:

| Domain | Model / Tool | Daily Limit & Refresh Cycle |
|---|---|---|
| Research | `coding-plan-search` | 15,000 / 5 hours |
| VLM (Vision) | `coding-plan-vlm` | 15,000 / 5 hours |
| Image | `image-01` | 120 / day |
| Lyrics | `lyrics_generation` | 100 / day |
| TTS | `Text to Speech HD` (`speech-2.8-hd`) | 11,000 / day |
| Music | `music-2.6` | 100 / day |
| Music | `music-2.5` | 4 / day |
| Music Cover | `music-cover` | 100 / day |
| Video | `Hailuo-2.3-Fast-768P-6s` | 2 / day |
| Video | `Hailuo-2.3-768P-6s` | 2 / day |

*Note: Video limits are extremely strict (only 2 per day per model). Music-2.5 is also limited to 4 per day. Plan your generations accordingly.*

## 6. Fail-Safe Operations & Error Handling
In the JS Fork (v0.0.18+), API errors are no longer obfuscated as generic HTTP 500 errors. If a quota is exceeded or a model is temporarily unavailable, the tool will return the exact API error string with an `isError: true` flag. 
**Agent Directive:** If you receive a plan/support error or quota exceeded error, do not hallucinate external tools (like HeartMuLa). Instead, gracefully execute a failover by retrying the tool with the designated fallback model.

## 7. Infrastructure Environment
- **Hosting:** Railway (Containerized Environment)
- **API Key Injection:** Managed securely via Railway Environment Variables (`${MINIMAX_API_KEY}`). The `config.yaml` intentionally leaves the key as a variable for the OpenClaw engine to interpolate at runtime.
- **Working Directory:** `/data/.hermes`

## Conclusion
You are not running a standard, out-of-the-box integration. You are operating a custom-tailored, highly optimized hybrid pipeline designed specifically to unlock the maximum potential of the Token Plan Max. Adhere strictly to the authorized models, respect your quota limits, and embrace the flexibility of your JS Media Node.

## 8. Brain Editor & File System (v1.4 Update)
The v1.4 update introduces a modern, mobile-native Brain Editor for managing agent files (`/data/.hermes`), prompts, and memory.
- **Dynamic CRUD:** Full support for file/folder creation via custom HTML modals, renaming/moving via path inputs, and safe deletions.
- **Neon "Hot" Indicator:** Files created or modified within the last 60 minutes are marked with a CSS-driven glowing neon cyan indicator and relative timestamps (e.g. `3 dk önce`), making it easy to identify newly generated media or configuration changes.
- **Quick Navigation:** Instant access shortcuts to `@WORKSPACE` (Code generation output), `@DATA` (Internal agent memory/config), and `@ROOT` (System level).
- **Time Drift Tolerance:** Relative time calculations automatically tolerate Railway's server-client clock skews up to 24 hours (if the server is ahead), ensuring accurate "Just now" reporting.

## 9. Project Origins & Repositories
To fully understand your own architecture, you must be aware of the upstream repositories and components that form your foundation:
- **Core Agent (Upstream):** `NousResearch/hermes-agent` — This is the core intelligence and orchestration engine you run on. It provides the base capabilities for tool use and conversational memory.
- **Media MCP (Custom Fork):** `algorytma/MiniMax-MCP-JS` — This is a critical fork of the official MiniMax MCP JS server. It was heavily modified by us to remove hardcoded model restrictions, add robust error reporting (`isError: true`), and implement the local storage bypass for seamless media rendering.
- **Base UI & Gateway:** `praveen-ks-2001/hermes-agent-template` — The original Railway-ready wrapper that provided the `config.yaml` injection and initial UI, which we extensively modernized.
- **This Repository:** `algorytma/hermes-minimax-railway-template` — Your current home. This template combines the core Hermes agent, our custom JS Media MCP, the official Python Research MCP, and the custom Brain Editor into a single, unified, production-ready environment optimized for Token Plan Max.

## 10. Upgrades & Rollbacks (Railway Docker Strategy)
Because we operate in a containerized environment (Docker) on Railway, pulling upstream updates from the core `NousResearch/hermes-agent` and handling rollbacks must be done systematically to ensure stability.

### Upgrading Hermes Agent
The core agent code is fetched during the Docker build process. 
1. **The `HERMES_REF` Build Argument:** Open the `Dockerfile` in the root of our template. At the top, you will see `ARG HERMES_REF=main`. 
2. **Bleeding Edge vs Stable:** By default, it is set to `main`, meaning every time you trigger a new deployment on Railway, Docker will fetch the absolute latest commit from the official NousResearch repository.
3. **Locking to a Stable Version:** If `main` introduces breaking changes, you should change `ARG HERMES_REF=main` to a specific stable release tag (e.g., `ARG HERMES_REF=v2026.4.23`). Check the official [Hermes Releases](https://github.com/NousResearch/hermes-agent/releases) page for the latest stable tag.
4. **Triggering the Update:** Once you update the `Dockerfile` and push to GitHub, Railway will automatically rebuild the container, pulling down the specified version of Hermes.

### Executing a Rollback
If a new deployment breaks the agent (e.g., due to an unstable upstream commit or a bug in our custom UI), rolling back is a one-click process on Railway:
1. **Railway Dashboard:** Go to your project on Railway.app and click on the Hermes service.
2. **Deployments Tab:** Navigate to the "Deployments" tab to see your deployment history.
3. **Rollback:** Find the last known working deployment (it will have a green success badge). Click the three dots (`...`) next to it and select **Redeploy** or **Rollback**.
4. **Instant Restore:** Railway will instantly spin up the Docker image from that exact point in time. Because our `/data` folder is mounted as a persistent volume, **your files, memory, and database are completely safe** during a rollback. The rollback only reverts the application code, not your data.
