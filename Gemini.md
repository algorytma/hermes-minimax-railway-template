# Gemini (Antigravity) Ajan Oryantasyon ve Kişiselleştirme Rehberi

Merhaba! Eğer bu projeye atanmış yeni bir yapay zeka asistanıysan (Gemini / Antigravity), burası senin **Ana Kontrol Merkezindir.** 
Kullanıcının (Emre) senden beklentileri, iletişim tarzı ve projeye yaklaşımın aşağıdaki global kurallara dayanmalıdır:

## 1. İletişim ve Dil Kuralları
- **Dil:** Benimle iletişim kurarken istisnasız **her zaman Türkçe** konuş.
- **Karakter:** Yanıtlarında son derece net, kısa ve öz ol. Suyu bulandırma, lafı uzatma ve gereksiz tekrarlardan kaçın. Felsefe yapmadan doğrudan çözüme odaklan.

## 2. Geliştirme ve Proje Bağlamı
- **Proje Karakteri:** Bu proje genellikle bir **"Wrapper / Template"** tarzı yapı olarak çalışmaktadır. Yeni teknolojileri hızlıca paketleyip deploy etmeye (Railway üzerinden) olanak sağlar.
- **Kodlama Standartları:** Kod yazarken her zaman modern, temiz ve modüler bir mimari benimse.
- **Güvenlik (Kritik):** Projede zaten "Çalışan" sistemler vardır. Benden (Kullanıcıdan) açıkça talep gelmedikçe var olan ve çalışan kod bloklarını **asla bozma,** sadece istenen spesifik güncellemeyi yap.

## 3. "Bana Sürekli Aynı Şeyleri Sorma!" (Taşınabilirlik Kılavuzu)
Geliştirme ortamı (Bilgisayar, IDE, Ajan) değişse bile proje standartları sabittir. Sistemi anlamak için her seferinde geliştiriciye soru sorma, aşağıdaki 3 dosyaya bak:
1. **`.cursorrules`:** Sistemin nasıl deploy edildiğini (Railway), kodların nasıl commitlenip gönderileceğini ve environment (.env) farklarını oradan öğren.
2. **`docs/INFRA_MANIFEST.md`:** Projenin mimarisi, yapısı ve iskeleti buradadır. Projeye başlarken bu manifestoyu oku.
3. **`.env`:** Tüm hassas bilgiler (API Keyler, Tokenler) buradadır ve **asla** repoya aktarılmaz (GitHub'a pushlanmaz).

## 4. Yetki Sınırları ve İnisiyatif
- Proje içerisindeki işlemleri, **Antigravity Customization** ve `.cursorrules` dosyasına sadık kalarak otonom yürütebilirsin.
- Eğer büyük bir dosya değişikliği (`server.py` gibi) yaptıysan, kendi token (Context) limitlerini aşmamak için MCP araçları (Örn: github-mcp-server) kullanmak yerine, işlemi lokalde `run_command` üzerinden `git push` ile tamamla.

*Bu dosya, seninle (Ajan ile) geliştirici arasındaki en önemli köprüdür. Okuduysan, işe koyulmaya hazırsın demektir.*
