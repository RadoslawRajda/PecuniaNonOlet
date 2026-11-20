# Przegląd bezpieczeństwa backendu

Zakres tego przeglądu to roboczy branch `feature/backend-hardening` oparty na
`feature/google-passkeys-auth`. Jest to ocena wdrożonych zmian i pozostałych
ryzyk, nie deklaracja zgodności ani certyfikacja OWASP ASVS.

## Zmiany w tej iteracji

| Obszar | Zastosowanie / dowód | Status i ograniczenie |
|---|---|---|
| Ochrona wyzwań WebAuthn | `app/routes/passkeys.py`: walidacja challenge i typu client data, wymaganie `userHandle` dla discoverable login, odrzucenie `crossOrigin` i `topOrigin`; wyzwania rejestracji są związane z sesją | Test integracyjny tworzy lokalny klucz P-256 i poprawnie podpisane registration/assertion, po czym sprawdza `py_webauthn`; błędny podpis jest odrzucany. Nie uruchomiono ceremonii na fizycznym urządzeniu. |
| Trwały uchwyt WebAuthn | Migracja `migrations/versions/0010_auth_identity_hardening.py` dodaje nieprzewidywalny `webauthn_user_handle`, zachowując dotychczasowe uchwyty kont z passkeys | Testy migracji przechodzą. Brak niezależnego testu zgodności na reprezentatywnej kopii produkcyjnej bazy. |
| Google OIDC | `app/routes/google_auth.py` rozpoznaje istniejące powiązanie issuer+subject przed polityką provisioningu. `app/adapters/google_oidc.py` ogranicza transport do stałego endpointu certyfikatów Google, timeoutu 5 s, bez redirectów i cache respektującego `Cache-Control` (maks. 6 h) | Testy podpisu tokenu, czasu ważności, cache i błędów transportu przechodzą. Rzeczywistego pobrania certyfikatów Google nie wykonano. |
| Konta bez hasła lokalnego i świeże uwierzytelnienie | Migracje zapisują `has_local_password`, metodę uwierzytelnienia sesji i zweryfikowany `auth_time` Google oddzielnie od czasu utworzenia sesji; MFA przenosi kontekst źródłowego uwierzytelnienia | Testy odrzucają stare `auth_time` i sprawdzają świeży przepływ Google→TOTP. Brak `auth_time` pozwala na zwykłe logowanie, ale nie na zmianę metod bezpieczeństwa. |
| TOTP i kody odzyskiwania | `app/totp.py` używa RFC 6238: SHA-1, 6 cyfr, 30 sekund, unikalny losowy sekret na konto; sekret jest szyfrowany AES-256-GCM z AAD wiążącym konto i przeznaczenie. Weryfikacja dopuszcza bieżący i poprzedni krok, nigdy przyszły; `last_used_step` blokuje ponowne użycie, próby są limitowane, a kody odzyskiwania są jednorazowe | Testy granic czasu, replay, limitów, szyfrowania, kodów odzyskiwania i równoległego użycia; zachowanie odpowiada wskazówkom OWASP MFA dla okna TOTP i ochrony sekretu. Nie sprawdzono HSM/KMS; lokalny klucz z `.env` pozostaje obowiązkiem operatora. |
| Redakcja błędów walidacji | Handler błędów FastAPI usuwa `input`, `ctx` i `url` z odpowiedzi 422; testy obejmują poufne wejścia | Testy przechodzą; brak pełnej inspekcji wszystkich loggerów i zewnętrznej telemetrii. |
| Audyt i wyzwania | Wpisy bezpieczeństwa dla łączenia Google oraz rejestracji/usunięcia passkey; wyzwania związane z sesją tam, gdzie potrzebne | Niepowodzenia logowania i odrzucenia wyzwań nie mają odrębnego, trwałego kanału audytu. Nie logować sekretów ani całych credentials. |
| Limity body | `app/request_limits.py` liczy strumień ASGI: zdjęcia 2 MiB + narzut, passkeys 32 KiB, Google auth 10 KiB | Testy obejmują `Content-Length` i przekroczenie limitu przez fragmenty bez nagłówka. Limity proxy/serwera nadal zależą od wdrożenia. |
| Throttling | `app/rate_limits.py` utrwala liczniki w SQLite; obejmuje rejestrację, hasło, Google, MFA i passkeys przed kosztowną weryfikacją | Testy obejmują współdzielenie przez połączenia DB i 429 przed verifierem hasła. Klucze to SHA-256 (nie tajny HMAC); wiele węzłów wymaga wspólnego magazynu i spójnych blokad. |
| CAPTCHA | `app/adapters/turnstile.py` ma stały URL providera, timeout 5 s, walidację `success`, hosta i akcji; błędy sieci zamienia na 503 | Osobne testy adaptera obejmują brak konfiguracji, `success=false`, timeout, zły host/akcję, zły kształt i uszkodzoną odpowiedź; testy rejestracji jawnie stubują verifier. |
| Ustawienia i składanie aplikacji | `app/config.py` definiuje typowane ustawienia Pydantic i walidację profilu production; `main.create_app(settings)` przekazuje konfigurację do request context i migracji; production wymaga jawnego `TRUSTED_HOSTS`, wyłącza publiczne docs i lokalną stronę/CA, waliduje Host | Testy konfiguracji env, redakcji sekretów, blokowania developerskich wartości, docs, Host i custom database path | Potwierdzone w testach jednostkowych i TestClient; konfiguracja deploymentu nadal musi ustawić rzeczywistą listę hostów. |
| Passkey API klienta | `src/auth/authMethods.ts` wysyła `POST` dla pobrania opcji; test sprawdza pierwszy request | Test Jest przechodzi. Nie wykonano builda ani testu natywnego iOS/Android. |
| Zależności i powtarzalne instalacje | `requirements-runtime.lock.txt` blokuje runtime, a `requirements.lock.txt` blokuje środowisko testowe; FastAPI `0.165.0` i Starlette `1.10.0`, Pillow `13.0.0` | `pip-audit -r requirements.lock.txt`: `No known vulnerabilities found`. Wcześniejszy zestaw raportował podatności dla Starlette `0.46.2` i Pillow `12.3.0`. Wynik zależy od aktualności bazy advisories. |
| Lokalne Associated Domains | Entitlement zawiera `webcredentials:pecunianonolet.local?mode=developer`; `launcher.py --aasa-only` udostępnia tylko AASA i Android Asset Links przez TLS na standardowym porcie 443 | Testy sprawdzają entitlement bez portu, konfigurację TLS/443, dopuszczone ścieżki oraz dokumenty JSON. Do lokalnego testu iPhone’a potrzebne są uprawnienia do zbindowania portu 443, aplikacja developerska i `Associated Domains Development`; nie wykonano testu na fizycznym urządzeniu. |
| Usługi finansowe i adapter NBP | `app/services/transfers.py` i `app/services/exchanges.py` przejęły transakcyjne wykonanie transferu/wymiany; klient NBP jest w `app/adapters/nbp_rates.py` | Istniejące testy transakcji, współbieżności, idempotencji, dokładności i rollbacku przechodzą | Wycena i część zapytań/odpowiedzi pozostają w `routes/exchange.py`; pełna separacja repozytoriów nie jest celem tej iteracji. |

## Wyniki weryfikacji

- `python -m pytest -q`: **167 passed** na Pythonie 3.11, 3.12 i 3.13. Macierz wersji została sprawdzona lokalnie; osobno świeżo utworzone środowisko z `requirements.lock.txt` przeszło cały zestaw na Pythonie 3.13.
- `ruff check app tests launcher.py`: **passed** na Pythonie 3.11, 3.12 i 3.13; potwierdzone również na świeżym środowisku lockfile.
- `ruff format --check app tests launcher.py`: **54 pliki poprawnie sformatowane** na Pythonie 3.11, 3.12 i 3.13; potwierdzone również na świeżym środowisku lockfile.
- `mypy app`: **Success, no issues found in 37 source files** na Pythonie 3.11, 3.12 i 3.13; potwierdzone również na świeżym środowisku lockfile.
- `pip-audit -r requirements.lock.txt`: **No known vulnerabilities found**.
- `jest --runInBand --config jest.config.js __tests__/authMethods.test.ts`: **2 passed**.
- Macierz workflow (testy, Ruff, mypy i audyt zależności) została odwzorowana lokalnie na Pythonie 3.11/3.12/3.13. Nie potwierdzono uruchomienia workflow w GitHub Actions.
- Nie wykonano pełnego buildu React Native ani end-to-end na fizycznym urządzeniu.
- Testy używają `httpx2`, rekomendowanego przez aktualny Starlette TestClient; pełny zestaw przechodzi bez ostrzeżenia deprecacyjnego klienta.

## Wstępna macierz OWASP ASVS 5.0.0

To jest wycinek dla kontroli dotkniętych zmianami i typowych dla API bankowego. Statusy odnoszą się do dowodów dostępnych w tym branchu; „częściowo” i „brak dowodu” nie oznaczają spełnienia wymagania. Identyfikatory i poziomy pochodzą z oficjalnego wydania ASVS 5.0.0. Pełna ocena wszystkich wymagań L2 pozostaje otwarta.

| Wymaganie | Zastosowanie i kod/polityka | Test/dowód | Status / ograniczenie |
|---|---|---|---|
| v5.0.0-V1.3.6 (L2), SSRF | Google cert adapter używa stałego hosta Google, timeoutu i wyłącza przekierowania; provider NBP ma stały URL | Testy adaptera Google: URL, timeout i cache; testy kursów NBP | Częściowo; brak pełnego testu sieciowego/egress policy wdrożenia |
| v5.0.0-V2.3.4 (L2), atomowość ograniczonych zasobów | Operacje finansowe używają blokady `BEGIN IMMEDIATE`, warunkowego debit i idempotencji | Testy współbieżności, rollbacku i idempotencji transferów/wymiany | Potwierdzone w pokrytym zakresie; nie jest to całościowy przegląd wszystkich reguł domenowych |
| v5.0.0-V3.4.2 (L1), CORS | API nie używa cookies do sesji; klient natywny wysyła opaque bearer token | Przegląd konfiguracji app | Brak jawnego middleware CORS; dla obecnego klienta nie jest potrzebny, ale obsługa przeglądarkowego klienta wymaga osobnego przeglądu |
| v5.0.0-V3.5.1 (L1), ochrona żądań cross-origin | Brak cookie-auth/CSRF tokenów; operacje zmieniające stan używają POST/PUT/DELETE i bearer auth | Testy kontraktów metod i autoryzacji | Częściowo; nie wykonano pełnych testów przeglądarkowych Origin/Sec-Fetch |
| v5.0.0-V3.5.3 (L1), metody dla operacji wrażliwych | Auth i operacje zmieniające stan używają metod niebezpiecznych HTTP | Test metod auth/passkeys, w tym pierwszy request klienta | Potwierdzone dla objętych testem endpointów; nie jest to automatyczny skan wszystkich tras |
| v5.0.0-V5.2.1 (L1), limity uploadu | Body zdjęcia ograniczone do 2 MiB + narzut, obraz jest walidowany i ponownie kodowany | Testy oversized, chunked body i limitów wymiarów | Potwierdzone dla zdjęć; proxy/server limits pozostają wdrożeniowe |
| v5.0.0-V6.1.1 (L1), dokumentacja throttlingu | Utrwalone limity SQLite obejmują login, Google, MFA i passkeys; konfiguracja szczegółów limitów jest w `app/rate_limits.py` | Testy limitów i 429 przed weryfikacją hasła | Częściowo; wiele hostów wymaga wspólnego magazynu i spójnych blokad |
| v5.0.0-V6.1.3 (L2), równoważność ścieżek auth | Wspólny etap MFA i kontekst metody auth dla password/Google/passkey | Testy przepływów Google→TOTP, passkey i świeżego `auth_time` | Częściowo; brak testu end-to-end AppAuth na urządzeniu |
| v5.0.0-V6.2.3 (L1), zmiana hasła | Zmiana istniejącego hasła wymaga aktualnego dowodu; Google-only ustawia pierwsze hasło po świeżym uwierzytelnieniu | Testy współbieżności i Google-only | Częściowo; świeżość Google zależy od zweryfikowanego `auth_time` i konfiguracji klienta Google |
| v5.0.0-V6.2.4 (L1), słabe hasła | Obecna walidacja ogranicza długość, lecz nie sprawdza listy co najmniej 3000 popularnych haseł | Brak testu listy haseł | Niespełnione; wymaga doboru lokalnej/zarządzanej listy i testów bez wysyłania haseł do zewnętrznego serwisu |

Źródła: [OWASP ASVS 5.0.0](https://asvs.owasp.org/downloads/), [OWASP MFA Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html), [RFC 6238](https://www.rfc-editor.org/rfc/rfc6238), [W3C WebAuthn Level 3](https://www.w3.org/TR/webauthn-3/) i [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html). Ta macierz nie jest deklaracją zgodności ani certyfikacją.

## Otwarte ryzyka przed uznaniem backendu za gotowy

1. **CI:** workflow ma macierz Python 3.11/3.12/3.13, instaluje `requirements.lock.txt` i wykonuje pytest, Ruff, mypy oraz pip-audit. Testy, Ruff i mypy wykonano lokalnie na trzech wersjach; środowisko lockfile sprawdzono dodatkowo na Pythonie 3.13, a audyt pip-audit uruchomiono dla lockfile. Nie potwierdzono wyniku jobów z GitHub Actions.
2. **Konfiguracja i architektura:** istnieje `create_app(settings)` i typowany profil dev/test/prod. Składanie aplikacji, auth/diagnostyka, wspólne kroki auth/MFA, magazyn zdjęć, wykonanie transferu i wymiany oraz adapter NBP zostały wydzielone; routery nadal zawierają część SQL i orkiestracji, szczególnie wycenianie, Google i passkeys. Brakuje pełnego wydzielenia repozytoriów i kompletnego opisu DTO/OpenAPI.
3. **Audyt nieudanych prób:** skuteczne zmiany bezpieczeństwa są audytowane, ale odrębny trwały strumień dla odrzuconych logowań/challenge nie został dodany.
4. **Dowody standardów:** powyższa macierz jest wycinkiem, nie kompletną oceną wszystkich wymagań ASVS L2. W szczególności kontrola popularnych haseł v5.0.0-V6.2.4 pozostaje niespełniona; pozostałe wymagania także muszą być ocenione, a każde N/A uzasadnione.

## Otwarte ustalenia przeglądu

### SEC-01 — Średnie: brak kontroli popularnych haseł

- **Lokalizacja:** `app/schemas.py`, `RegisterCredentials.password` i `ChangePasswordRequest.new_password`.
- **Dowód:** modele wymagają obecnie długości 8–128 znaków, ale nie porównują hasła z lokalną listą popularnych lub skompromitowanych haseł.
- **Wpływ:** użytkownik może ustawić hasło łatwe do zgadnięcia lub obecne w wyciekach; ogranicza to skuteczność ochrony konta opartego na haśle.
- **Następny krok:** dodać sprawdzaną lokalnie listę obejmującą co najmniej 3000 popularnych haseł i testy rejestracji oraz zmiany hasła. Hasła nie mogą być wysyłane do zewnętrznego sprawdzacza.
- **Obecne ograniczenia:** minimum długości, Argon2id, throttling prób, Turnstile przy rejestracji i opcjonalne MFA zmniejszają ryzyko, ale nie spełniają kontroli ASVS v5.0.0-V6.2.4.

## Wniosek

Zmiany usuwają potwierdzone błędy auth, dodają trwałe limity prób i rozmiaru żądań, testują podpisy WebAuthn i Google `auth_time`, aktualizują zależności podatne na znane advisory, dodają typowaną konfigurację i mypy do CI. Lokalne Associated Domains są skonfigurowane do developmentu przez port 443, ale wymagają weryfikacji na fizycznym iPhonie. Cel hardeningu pozostaje otwarty: dalsze wydzielenie architektury, pełna macierz OWASP ASVS 5.0.0 L2, sprawdzenie popularnych haseł, pełny build mobilny i rzeczywiste uruchomienie workflow w CI wymagają zakończenia.
