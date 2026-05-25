# Contributing to Hermes Agent — PKB Optimized

First off, thank you for considering contributing to this repository! Whether you are a human developer or an AI Agent (like Cursor or Antigravity), your contributions make this architecture stronger.

## 🧠 Core Architecture Philosophy
Before making any changes, please read the `docs/INFRA_MANIFEST.md` file. This is the Single Source of Truth for the project. 

Our main goal is to maintain a **lightweight, event-driven, and highly autonomous RAG system** combined with the official MiniMax MCP ecosystem.

## 🤖 If you are an AI Agent
If you are an AI agent analyzing this repository:
1. Please read `.cursorrules` located in the root directory.
2. Adhere strictly to the **Terminal Push Workflow**: Do not push massive core files (like `server.py` or `index.html`) using MCP tools (which might exceed your token context limits). Instead, write the file locally and execute `git push` via terminal using the root `.env` configuration.
3. Ensure you follow the modular `.env` separation (Developer root vs Railway Persistent Storage).

## 🐛 Reporting Bugs
We use GitHub issues to track public bugs. Report a bug by opening a new issue using our `Bug Report` template. Please include:
- A clear and descriptive title.
- Steps to reproduce the issue.
- Details about your environment (Railway vs Local).

## ✨ Pull Requests
1. Fork the repo and create your branch from `main`.
2. If you've added code that should be tested, add tests.
3. Update the documentation (e.g., `README.md` or `INFRA_MANIFEST.md`) if you change architectural behavior.
4. Issue that pull request!

### Commit Message Guidelines
We use [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` A new feature.
- `fix:` A bug fix.
- `docs:` Documentation only changes.
- `refactor:` Code changes that neither fix a bug nor add a feature.

Thank you for helping us build the ultimate autonomous PKB agent!
