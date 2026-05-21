# Proje Geliştirme Bağlamı
- Proje manifest dokumani /docs dizini icinde INFRA_MANIFEST.md dosyasindadir.
- Bu proje "Hermes Railway Template" (Python FastAPI/Starlette) projesidir.
- Yapılandırma dosyaları `.env` veya `/data/.hermes` içerisinde tutulmaktadır.
- Projede veritabanı bağlantısı bulunmuyor; yapılandırmalar `config.yaml` ve dosya sistemi (JSON) üzerinden yürütülüyor.

# İş Akışı ve Deployment Otomasyonu (ÖNEMLİ)
- Benden bir kodlama görevi istendiğinde ve geliştirme başarıyla tamamlandığında işlemi bitirmek için şu adımları her zaman uygula:
  1. Yaptığın değişiklikleri `git add .` ile ekle.
  2. Anlamlı bir mesajla `git commit -m "feat/fix: yapılan işin özeti"` at.
  3. Railway deployment'ını tetiklemek için `git push origin main` komutunu çalıştır.
- Bu push işlemi başarılı olduktan sonra kullanıcıya işlemin bittiğini ve Railway'de deploy'un başladığını bildir.
Yes.
