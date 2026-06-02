# Hermes Agent Knowledge Base & Roles

This file defines your expertise and rules for navigating the workspace.

## Directories
- `00_Inbox/`: Gelen fikirler, ham notlar ve ajan tarafından oluşturulan tüm taslaklar.
- `10_Daily_Notes/`: Günlük notlar ve günlük kayıtlar.
- `20_Projects/`: Aktif projeler ve çalışma alanları.
- `30_Knowledge_Base/`: Kalıcı bilgi tabanı ve referans dokümanları.

## Directives
- Yeni not veya fikir eklerken KESİNLİKLE `00_Inbox/` klasörünü kullanmalısın.
- Diğer klasörleri (`20_Projects/`, `30_Knowledge_Base/`) yalnızca okuma (read-only) amaçlı kullan.
- Notlarına mutlaka YAML frontmatter ekle ve notları anlamsal olarak birbirine `[[Not Adı]]` ile bağla.
- Bu dizin yapısının dışındaki (`projects/`, `knowledge_base/`, `private/` gibi) eski klasörleri görmezden gel ve kullanma.
