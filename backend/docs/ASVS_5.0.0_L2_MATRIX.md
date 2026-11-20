# OWASP ASVS 5.0.0 — macierz L2 (backend)

Źródłem identyfikatorów jest oficjalny [CSV OWASP ASVS 5.0.0](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv). Wydanie zawiera 183 wymagania poziomu L2. Lista poniżej jest checklistą do oceny tego backendu; sama obecność identyfikatora nie oznacza zgodności.

## Zasady oceny

- **Potwierdzone** — istnieje dowód w kodzie i aktualny, uruchomiony test lub niezależna weryfikacja.
- **Częściowo** — mechanizm istnieje, ale brakuje części pokrycia albo weryfikacji.
- **Brak** — wymaganie nie jest spełnione.
- **N/D** — wymaganie nie ma zastosowania do aktualnej architektury; uzasadnienie jest obowiązkowe.
- **Nieocenione** — nie ma wystarczającego dowodu. Nie jest to status zaliczenia.

W tej iteracji uruchomiono testy na przypiętych zależnościach dla Python 3.11, 3.12 i 3.13. To potwierdza działanie testów aplikacji, ale nie jest samodzielnym dowodem zgodności z każdym wymaganiem ASVS. N/D przypisano wyłącznie wymaganiom WebRTC (V17): backend nie implementuje połączeń RTC, sygnalizacji ani mediów. Pozostałe kontrole wymagają oceny względem konkretnego wdrożenia i testów.

## Wyniki testów dla backendu

- Python 3.11: `pytest` 188 passed; Ruff lint, Ruff format i mypy zaliczone.
- Python 3.12: `pytest` 188 passed; Ruff lint, Ruff format i mypy zaliczone.
- Python 3.13: `pytest` 188 passed; Ruff lint, Ruff format i mypy zaliczone.
- `pip-audit -r requirements.lock.txt`: brak znanych podatności w zablokowanych zależnościach przy ostatnim sprawdzeniu.
- Zakres nie obejmuje iOS/Android end-to-end, rzeczywistych zewnętrznych Google/Cloudflare/NBP, produkcyjnej konfiguracji TLS ani operacyjnego monitoringu.

Weryfikacje krytyczne wraz z dowodami są opisane w [przeglądzie bezpieczeństwa](SECURITY_REVIEW.md). Pozycje nadal oznaczone jako „Nieocenione” pozostają otwarte i nie są zaliczone.

## Priorytetowa ocena wymagań dotyczących API, uwierzytelniania i finansów

Ta tabela ocenia kontrole, które mają bezpośrednie zastosowanie do obecnych funkcji backendu. „Częściowo” oznacza, że kod/test istnieje, ale wskazany brak pozostaje otwarty. Katalog 183 wymagań poniżej jest szerszy i nie należy traktować go jako w pełni ocenionego.

| Wymaganie ASVS 5.0.0 L2 | Zastosowanie | Kod / polityka | Test / dowód | Ograniczenie lub wynik |
|---|---|---|---|---|
| V2.1.2, V2.1.3 | Tak: limity oraz spójność kwot i walut | `app/schemas.py`, `app/services/transfers.py`, `app/services/exchanges.py` | `tests/test_exchange.py`, `tests/test_app.py` | Częściowo: reguły limitów są w kodzie i README, lecz brak jednego kompletnego katalogu reguł biznesowych API. |
| V2.3.2, V2.3.3, V2.3.4 | Tak: przelewy, wymiana, MFA i jednorazowe wyzwania | Usługi finansowe używają `BEGIN IMMEDIATE`, walidacji pod blokadą i atomowego księgowania | `tests/test_exchange.py`, `tests/test_app.py`, `tests/test_mfa.py`, `tests/test_migrations.py` | Potwierdzone w testach SQLite; nie zastępuje testu obciążeniowego ani oceny produkcyjnego storage. |
| V2.4.1 | Tak: logowanie, challenges, MFA i API finansowe | `app/rate_limits.py`, limity per IP/tożsamość oraz wyzwanie | `tests/test_rate_limits.py`, `tests/test_exchange.py`, `tests/test_google_passkeys.py` | Częściowo: limity są trwałe w SQLite dla jednego lokalnego deploymentu; brak wspólnego limitera dla wielu węzłów. |
| V4.1.2, V4.1.3 | Tak: API HTTPS i nagłówki proxy | `launcher.py`, `app/local_tls.py`, `app/rate_limits.py`; forwarded IP nie jest ufany bez zaufanego proxy | `tests/test_launcher.py`, `tests/test_local_tls.py`, `tests/test_rate_limits.py` | HTTPS/mDNS zweryfikowano lokalnie; nie weryfikowano konfiguracji zewnętrznego reverse proxy. Endpoint API nie może po cichu przekierować żądania z wrażliwym body. |
| V4.2.1 | Tak, ale zależy od serwera i proxy | Granicę wiadomości obsługują Uvicorn/warstwa wdrożeniowa | Testy HTTP aplikacji nie sprawdzają parsera proxy ani HTTP/2/3 | Nieocenione operacyjnie; wymaga testu konkretnej konfiguracji sieciowej. |
| V4.3.1–V4.3.2 | Nie | Backend nie udostępnia GraphQL | Brak GraphQL routera w `app/main.py` | N/D dla bieżącego API; oceń ponownie po dodaniu GraphQL. |
| V4.4.2–V4.4.4 | Nie | Backend nie udostępnia WebSocket | Brak WebSocket routera w `app/main.py` | N/D dla bieżącego API; oceń ponownie po dodaniu WebSocket. |
| V5.1.1 | Tak: zdjęcia profilowe | `app/routes/profile_photos.py`, `app/photo_storage.py` | `tests/test_profile_photos.py`, `tests/test_request_limits.py` | Częściowo: ograniczenia MIME/formatu/rozmiaru/pikseli i re-encoding są opisane; nie ma skanera AV, oryginał nie jest udostępniany. |
| V5.2.3 | Nie | Backend przyjmuje wyłącznie pojedynczy obraz, nie archiwa | `tests/test_profile_photos.py` | N/D dla formatu uploadu; limity pikseli i bajtów są egzekwowane w aplikacji. |
| V5.4.1–V5.4.3 | Ograniczone | Zdjęcie jest zwracane jako znormalizowane JPEG z wewnętrznego identyfikatora | `tests/test_profile_photos.py` | Brak downloadów dowolnych plików. Nie skanujemy AV; operacyjne ryzyko ogranicza walidacja i ponowne kodowanie obrazu. |
| V6.1.2, V6.1.3 | Tak: hasło, Google, passkey i TOTP | `app/password_policy.py`, `docs/TOTP_MFA.md`, `README.md` | `tests/test_password_policy.py`, `tests/test_google_passkeys.py`, `tests/test_mfa.py` | Częściowo: ścieżki są opisane, ale MFA jest opt-in; nie ma polityki wymuszającej MFA na wszystkich kontach. |
| V6.2.9, V6.2.11 | Tak: polityka haseł | `app/schemas.py`, `app/password_policy.py`; akceptowane hasła do 128 znaków i blokowane słowa kontekstowe | `tests/test_password_policy.py`, `tests/test_app.py` | Potwierdzone dla istniejących ścieżek rejestracji i zmiany hasła. |
| V6.2.12 | Tak: sprawdzanie haseł wyciekłych | `app/resources/common-passwords.txt` zawiera lokalną listę 3000 haseł | `tests/test_password_policy.py` | Częściowo: to lista popularnych haseł, a nie pełny aktualizowany zbiór haseł z wycieków. |
| V6.3.3, V6.3.4 | Tak: wielościeżkowe logowanie | `app/routes/auth.py`, `google_auth.py`, `passkeys.py`, `mfa.py`; aktywne TOTP jest wymagane po każdym primary factor | `tests/test_google_passkeys.py`, `tests/test_mfa.py` | Częściowo: TOTP można włączyć dobrowolnie; pełne MFA nie jest domyślnie wymuszane. |
| V6.4.3, V6.4.4 | Tak dla odzyskiwania | Jednorazowe kody recovery istnieją, ale brak resetu hasła i weryfikacji tożsamości po utracie wszystkich czynników | `tests/test_mfa.py` | Brak procesu odzyskiwania przez operatora; użytkownik bez TOTP/passkey/recovery code może utracić dostęp. To otwarty wymóg przed wdrożeniem dla realnych kont. |
| V6.5.1, V6.5.3–V6.5.6 | Tak: TOTP i recovery codes | `app/totp.py`, `app/services/mfa.py`; CSPRNG, AES-GCM, 30-sekundowy TOTP, ochrona replay i rate limit | `tests/test_mfa.py` | Potwierdzone w testach; przechowywanie klucza MFA i recovery po utracie wymagają bezpiecznego procesu operacyjnego. |
| V6.5.2 | Tak: lookup secrets/recovery codes | Nowe recovery codes mają 128 bitów i SHA-256; wygenerowane poprzednią wersją kody mają 96 bitów | `tests/test_mfa.py` | Częściowo: stare kody są kompatybilne i nie można zmienić ich hashy bez wartości jawnych; potrzebna bezpieczna rotacja. |
| V6.5.5, V6.6.2, V6.6.3 | Tak: TTL, powiązanie i odporność na zgadywanie | Challenge 5 minut, TOTP 30 sekund, limity prób, jedno użycie | `tests/test_mfa.py`, `tests/test_rate_limits.py`, `tests/test_google_passkeys.py` | Potwierdzone w lokalnych testach integracyjnych. |
| V6.8.1, V6.8.2 | Tak: Google OIDC | Provider + issuer + subject, zweryfikowany podpis, iss/aud/azp/exp/nonce | `tests/test_google_passkeys.py`, `tests/test_google_oidc_adapter.py` | Test kryptograficzny działa na kluczu lokalnym; prawdziwy tenant Google i rotacja kluczy wymagają testu wdrożeniowego. |
| V6.8.4 | Tak: świeża reautoryzacja Google | `auth_time` jest wymagany i ograniczony do 5 minut dla operacji wrażliwych; brak claimu kończy się odmową | `tests/test_google_passkeys.py` | Zależne od poprawnego żądania claimu i konfiguracji Google; fizyczna integracja z dostawcą nie była testowana. |
| V7.1.1–V7.1.3 | Tak: polityka sesji | `docs/SECURITY_REVIEW.md`, `app/sessions.py`; access 15 min, refresh idle 30 dni, absolutnie 90 dni | `tests/test_app.py`, `tests/test_google_passkeys.py` | Dokumentacja określa pięć sesji i rotację; nie testowano retencji sesji w długotrwałym deploymentcie. |
| V7.2.1–V7.2.4 | Tak: opaque reference sessions | CSPRNG tokenów, hashe w bazie, backendowa kontrola każdej sesji | `tests/test_app.py`, `tests/test_google_passkeys.py` | Potwierdzone w testach; magazyn SQLite jest pojedynczym węzłem. |
| V7.3.1–V7.3.2 | Tak: timeouty | 15-min access, 30-dniowy idle refresh, 90-dniowa granica absolutna | `tests/test_app.py` | Potwierdzone na poziomie serwera; klient mobilny musi bezpiecznie obsłużyć rotację i utratę refresh tokenu. |
| V7.4.1, V7.4.3, V7.5.1–V7.5.2 | Tak: wylogowanie, zmiany poświadczeń i zarządzanie sesjami | `app/sessions.py`, `app/routes/sessions.py`; reauth i revocation | `tests/test_app.py`, `tests/test_google_passkeys.py`, `tests/test_mfa.py` | Backend potwierdzony testami; nie wykonano testu na fizycznym urządzeniu. |
| V8.2.1–V8.2.3, V8.3.1 | Tak: BOLA/role/field access | Własność sprawdzana w zapytaniach i przez zależności backendowe, niezależnie od UI | `tests/test_app.py`, `tests/test_analytics.py`, `tests/test_profile_photos.py` | Potwierdzone dla przeglądanych endpointów/testów; brak niezależnego testu penetracyjnego całego API. |
| V16.4.1–V16.4.3 | Tak: audyt i logowanie bezpieczeństwa | `app/audit.py`, `app/security_events.py`; sekretów ani body żądań nie zapisuje | `tests/test_audit.py`, `tests/test_app.py` | Częściowo: baza lokalna nie jest centralnym, odpornym na administratora systemem; brak retencji, alertów i monitoringu. |

| ASVS 5.0.0 ID | Status | Dowód / uzasadnienie |
|---|---|---|
| V1.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.2.6 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.2.7 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.2.8 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.2.9 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.6 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.7 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.8 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.9 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.10 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.11 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.4.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.4.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.5.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.1.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.4.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.4.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.4.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.4.6 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.5.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.5.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.7.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.7.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.1.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.2.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.3.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.4.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.4.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V5.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V5.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V5.4.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V5.4.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V5.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.1.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.2.9 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.2.10 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.2.11 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.2.12 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.4.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.5.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.5.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.5.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.5.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.5.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.6.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.6.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.6.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.8.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.8.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.8.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.8.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.1.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.3.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.4.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.4.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.5.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.5.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.6.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.6.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V8.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V8.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V8.4.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V9.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V9.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V9.2.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.2.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.3.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.4.6 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.4.7 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.4.8 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.4.9 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.4.10 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.4.11 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.5.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.5.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.5.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.5.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.5.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.6.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.6.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.7.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.7.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.7.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.2.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.4.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.4.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.5.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.6.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V12.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V12.1.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V12.3.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V12.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V12.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V12.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.2.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.2.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.2.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.3.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.4.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.4.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.4.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.2.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.1.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.3.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.3.6 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.3.7 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.2.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.2.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.2.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.3.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.4.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.4.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.5.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.5.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.5.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V17.1.1 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |
| V17.2.1 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |
| V17.2.2 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |
| V17.2.3 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |
| V17.2.4 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |
| V17.3.1 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |
| V17.3.2 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |

## Zakres i ograniczenia

Macierz zawiera komplet wymagań L2 z wydania 5.0.0, ale statusy „Nieocenione” oznaczają otwartą pracę. Nie wolno raportować backendu jako zgodnego z ASVS L2 na podstawie tej macierzy. Następny krok to ocena każdego wymagania pod kątem API, aplikacji mobilnej i konfiguracji uruchomieniowej, przypisanie dowodów testowych oraz formalne uzasadnienie każdego N/D.

