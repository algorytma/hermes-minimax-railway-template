# Antigravity Git Push ve MCP Kullanım Kuralları

1. **Küçük Çaplı ve Dokümantasyon Güncellemeleri:** Ajan (Antigravity), `AGENTS.md`, `.agent/rules/` dosyaları veya ufak çaplı `markdown` (not) değişiklikleri gibi hafif metin dosyalarını GitHub'a gönderirken, doğrudan **`github-mcp-server`** (MCP) aracındaki `push_files` veya `create_or_update_file` komutlarını kullanacaktır.
2. **Büyük Çaplı ve Ana Kod (Core) Güncellemeleri:** `server.py`, `index.html` gibi binlerce satırlık ana kod dosyalarının tamamını MCP'ye yüklemek (JSON parametresi olarak basmak) yapay zeka token/context sınırlarını aşacağından ve dosyayı bozma riski taşıdığından; büyük çaplı güncellemeler daima projenin kendi terminali üzerinden (`run_command` ile `git push`) ve `.env` (örneğin `/data/.hermes/.env`) dosyasındaki yerel `GITHUB_TOKEN` kullanılarak yapılacaktır.

*Bu dosya bizzat Antigravity MCP (github-mcp-server) kullanılarak oluşturulmuş ve doğrudan GitHub API ile repoya pushlanmıştır.*