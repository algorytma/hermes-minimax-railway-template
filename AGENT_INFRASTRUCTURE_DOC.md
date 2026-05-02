# HERMES: INFRASTRUCTURE & ARCHITECTURE DOCUMENTATION (v1.2)

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
