# Hermes-MiniMax Altyapı Manifestosu & Mimarisi (v1.6)

Bu belge, Hermes ajanının özel mimarisi için **Tek Gerçeklik Kaynağı (Single Source of Truth)** ve **Altın Standart (Gold Standard)** işlevini görür.
İki temel işlevi sorunsuzca birleştirir:
1. **Geliştirici Ajanlar (IDE)**: Kod yazmadan önce mimari taslağı anlamaları için.
2. **Çalışma Zamanı Yapay Zekası (Hermes) & UI Güncelleme Analizörü**: Yukarı akış (upstream) versiyon güncellemeleri sırasında web paneli üzerinden "Yapay Zeka Etki Analizi (AI Impact Analysis)" gerçekleştirmek ve sistem bütünlüğünü sağlamak adına birincil referans noktası olarak hizmet etmek için.

Herhangi bir sistem güncellemesi veya geliştirme oturumu sırasında, bu bileşenler dikkatle korunmalı veya uyarlanmalıdır.

---

## 1. Proje Kimliği & Versiyonlama
- **Mevcut Çekirdek (Core) Versiyon**: Kök `Dockerfile` içerisindeki `ARG HERMES_REF` üzerinden takip edilir.
- **Amaç**: Native MiniMax desteği, çoklu model yedekleme (fallback) mekanizması ve güçlü bir kalıcı dosya sistemi ile Railway dağıtımı (deployment) için optimize edilmiş özel bir Hermes Ajanı şablonu.
- **Repolar (Repositories)**:
  - **Çekirdek Ajan (Core Agent)**: `NousResearch/hermes-agent`
  - **Medya MCP**: `algorytma/MiniMax-MCP-JS` (Özel JS Forku)
  - **Bu Şablon**: `algorytma/hermes-minimax-railway-template`

---

## 2. Kalıcılık (Persistence) Haritası & Yapılandırma Birleştirme Stratejisi
Sistem geçici (ephemeral) bir Railway Docker konteynerinde çalışır. **TÜM veriler `/data` (`HERMES_HOME`) dizinine kaydedilmelidir.**
- **Çalışma Dizini**: `/data/.hermes/`
- **config.yaml**: `server.py` tarafından **PyYAML deep merge** kullanılarak yönetilir. `config.yaml` dosyasına yapılan manuel düzenlemeler korunur. Sistem komutu (system prompt) artık `config.yaml` içerisinde değildir.
- **SOUL.md**: `/data/.hermes/SOUL.md` yolunda bulunur (Sistem komutu için Slot #1).
- **.env**: Sistem düzeyindeki çevresel değişkenleri (örn. API anahtarları, Token'lar) içerir. Git'ten hariç tutulmuştur.
- **Durum & Kayıt Noktaları (State & Checkpoints)**: `/data/.hermes/state.db` ve `/data/.hermes/checkpoints/`
- **mcp-output**: `/data/.hermes/mcp-output/` (Medyalar için API'nin 5 dakikalık URL sona erme süresini atlar).

### Manifesto Tohumlama (`INFRA_MANIFEST.md`)
Başlangıçta, `server.py` `/data/.hermes/docs/INFRA_MANIFEST.md` dosyasını kontrol eder. Eksikse, `/app/docs/` (Docker imajı) içerisinden kopyalar. Bu, kullanıcı değişikliklerinin üzerine yazılmadan ajanın her zaman kendi mimari yapısının farkında olmasını sağlar.

---

## 3. İkinci Beyin (PKB Sync) & Webhook/RAG Çalışma Alanı
Ajan, bir "İkinci Beyin" (Second Brain) olarak hareket etmesi için gizli bir GitHub reposuyla (örn. bir Obsidian Kasası) senkronize edilen özel bir çalışma alanı içerisinde faaliyet gösterir.
- **Yol**: `/data/.hermes/workspace/`
- **Yapı**: 
  - `knowledge_base/`: Ajan için alan (domain) bilgisi.
  - `projects/`: Kodların ve çıktıların üretildiği yer.
  - `private/`: Kullanıcının gizli notları (Ajan tarafından yoksayılır).
  - `AGENTS.md` / `hermes.md`: Yönergeler ve dizinler.
- **Olay Güdümlü (Event-Driven) Senkronizasyon**: Eski periyodik `pkb_sync_loop` yerine, `/api/webhook/github` üzerinden dinlenen bir Webhook mekanizması kullanılır. GitHub'a bir not pushlandığında:
  1. Sunucu anında `git pull --rebase` yapar.
  2. Hermes'in RAG altyapısı (Vector DB) tetiklenerek yeni markdown dosyaları indekslenir.
  3. Ajan, notlara "Okundu/İşlendi" (Metadata) etiketi bırakır ve sonsuz döngü (infinite loop) koruması eşliğinde güvenli bir şekilde `git push` ile GitHub'a geri gönderir.

---

## 4. Hibrit "Otoyol (Highway)" MCP Çözümü & Token Planı
Resmi Python MCP'sindeki kodlanmış model kısıtlamalarını aşmak için, Hibrit bir Mimari kullanılır:
1. **Araştırma Düğümü (Python)**: `uvx minimax-coding-plan-mcp` (Web Araması ve Görüntü İşleme / Vision işlemlerini yönetir).
2. **Medya Düğümü (Özel JS Forku)**: `npx -y algorytma/MiniMax-MCP-JS` (TTS, Video, Müzik işlemlerini yönetir). Bu fork enum doğrulamalarını kaldırır ve dinamik model enjeksiyonuna izin verir.

**Günlük Kotalar (Token Planı Maksimumları):**
- **Araştırma / VLM**: 5 saat başına 15.000.
- **Video (`Hailuo-2.3-Fast-768P-6s`)**: KESİNLİKLE günde 2 adet.
- **Müzik (`music-2.6`)**: Günde 100 adet.
- **TTS (`speech-2.8-hd`)**: Günde 11.000 adet.
*Ajan Yönergesi*: Plan oluşturma çağrılarını verimli yapın. Kotalar aşılırsa, harici araçlar uydurmak yerine zarif bir şekilde yedek (fallback) modellere geçilmelidir.

---

## 5. Beyin Editörü & Dosya Sistemi
Özel web paneli (dashboard), mobil uyumlu bir "Beyin Editörü" (Brain Editor) barındırır.
- **`resolve_path` Kısayolları (Aliases)**:
  - `@DATA` -> `/data/.hermes`
  - `@WORKSPACE` -> `/data/.hermes/workspace`
  - `@PROMPTS` -> `/app/prompts`
  - `@ROOT` -> `/`
- Kullanıcı arayüzünde her zaman bu kısayolları kullanın. Örn., "Edit Manifest" butonu `@DATA/docs/INFRA_MANIFEST.md` yolunu işaret etmelidir.

---

## 6. Yapay Zeka Etki Analizi & Otomatik Yama (Sistem Güncellemesi)
Güncellemeler, manuel terminal müdahalesini ortadan kaldıran ve güncelleme risklerini azaltan web panelinin "Sistem Güncellemesi" (System Update) modülü aracılığıyla akıllıca yönetilir.

### Changelog Ayrıştırma & Risk Değerlendirmesi
Herhangi bir güncellemeden önce, arayüz (UI) en son upstream sürümünü (Typeless/Hermes-Agent) çeker ve değişiklik günlüğünü (changelog) bu manifestoyla karşılaştırır:
- **Risk Tanımlaması**: Sistem kritik anahtar kelimeleri tarar (örn., "breaking" kelimesi kırmızı Kritik Risk oluşturur, "mcp" veya "tool" kelimesi token kullanımıyla ilgili Turuncu bir Uyarı tetikler).
- **Altın Standart Referansı (Gold Standard)**: Bu `INFRA_MANIFEST.md` dosyası, yapay zeka analizörü tarafından özel mimari bağımlılıklarını (Hibrit Otoyol MCP'si veya PKB Senkronizasyonu gibi) upstream değişikliklerine karşı çapraz kontrol etmek için aktif olarak referans alınır.

### Otomatik Yama Mekanizması
Kullanıcı, Yapay Zeka Etki Analizi raporunu inceleyip güncellemeyi onayladığında:
- **Mekanizma**: Arayüz, `/app/Dockerfile` dosyasını yerel olarak güvenle yamalar ve GitHub Contents API'si aracılığıyla (`ARG HERMES_REF=vX.Y.Z` güncelleyerek) doğrudan depoya (repo) bir commit göndermek için `GITHUB_TOKEN` kullanır.
- **Tetikleyici**: Railway yeni commit'i algılar ve otomatik olarak bir yeniden dağıtım (redeployment) başlatır.
- **Güvenlik**: `.gitignore`, gizli bilgilerin (secrets) sızmasını önlemek adına `.hermes/`, `data/` ve `config.yaml` dizinlerini açıkça hariç tutar.

---

## 7. Bilinen Hatalar (Bugs) & Sistem Kısıtlamaları
- **Ağ Geçidi (Gateway) Harici Yeniden Başlatma HATASI**: Hermes ağ geçidi (gateway), Yönetici Arayüzümüz (Admin UI) yerine yerel olarak (Hermes'in kendi arayüzü veya dahili çökme yoluyla) yeniden başlatılırsa, `Gateway` sınıfımız bir "error" (hata) durumu bildirir.
  - *Neden*: `--replace` yeni bir işlem başlattığında `_drain()` standart çıktı (stdout) bağlantısını (pipe) kaybeder.
  - *Mevcut Önlem*: `server.py` `pgrep -f "hermes.*gateway"` ve bilinen PID dosyalarını kullanarak işletim sistemi düzeyinde kontroller yapmaya çalışır, ancak bu bazen Railway konteyneri içerisinde başarısız olur. 
  - *Geliştiriciler İçin Not*: Sadece `self.proc.returncode` üzerine güvenmeyin. Düzeltiliyorsa, bilinen yerel bir uç noktaya (endpoint) yönelik yoklama/bekleme (polling) yapan bir sağlık kontrolü (healthcheck) düşünün.
- **`display.personality` Uyarısı**: Hermes ağ geçidi, eksik `agent.personalities` hakkında bir uyarı çıktısı verebilir. Bu zararsızdır; birleştirme (merge) mantığı kullanıcı ayarlarını doğru bir şekilde korur.
