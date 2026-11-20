# Raport prac nad backendem — R1–R12

## Punkt odniesienia i zakres

- Repozytorium: `RadoslawRajda/PecuniaNonOlet`.
- SHA review i dostępny zdalny HEAD `origin/feature/google-passkeys-auth`: `183ccd3ed338715d77821ba314fa901bf0876ab9`.
- Prace wykonano w izolowanym worktree na lokalnej gałęzi `feature/backend-hardening`. Nie wypychano jej na remote. Ostatni SHA kodu i testów: `269b0e31a43780810e364dffd6fc546741e1f083`.
- Zakres: backend FastAPI/Pydantic/sqlite3/Alembic oraz konieczne zmiany klienta sesji i reautoryzacji. Nie zmieniano technologii ani modelu opaque access/refresh tokens.
- Historyczne 188 testów z review to punkt odniesienia, nie wynik obecnego kodu.

## Stan wymagań

| Wymaganie | Stan implementacji i dowód | Ograniczenie |
|---|---|---|
| R1 — limit body przed operacją | `app/request_limits.py` odrzuca przekroczenie podczas odbioru strumienia. `tests/test_request_limits.py` sprawdza `Content-Length`, brak nagłówka, końcowy fragment, granicę, brak utworzonego użytkownika/sesji oraz brak zmiany salda, historii i księgi przy odrzuconym przelewie. | Test ASGI i endpointów, bez zewnętrznego proxy. |
| R2 — konfiguracja instancji | `app/config.py`, `app/database.py`, `migrations/env.py` i middleware korzystają z ustawień konkretnej aplikacji. `tests/test_config.py` sprawdza bazę B przy środowiskowej A, izolację instancji, limiter i security events. | CLI migracji korzysta z konfiguracji środowiskowej, gdy nie przekazano obiektu ustawień. |
| R3 — blokujące I/O security events | `app/security_events.py` przenosi zapis SQLite z event loop do threadpool. `tests/test_security_events.py` sprawdza postęp pętli podczas oczekiwania na zapis. Audyt finansowy pozostaje w transakcji operacji. | Błąd zapisu zdarzenia jest obserwowalny przez logger; lokalny log SQLite nie jest centralnym systemem audytu. |
| R4 — historyczne Google-only | Migracja `0015_legacy_password_origin.py` oznacza niejednoznaczny stan dawnych kont. Świeży Google `auth_time` pozwala ustanowić hasło lub TOTP bez nieznanego sekretu. `tests/test_legacy_google_passwords.py` obejmuje bazy 0009/0014 i zachowanie istniejących danych. | Konta o niejednoznacznym pochodzeniu wymagają dodatkowego potwierdzenia Google, nie są automatycznie klasyfikowane jako Google-only. |
| R5 — Google reauth | `app/services/google_accounts.py` wymaga zweryfikowanego, świeżego `auth_time`, powiązanego issuer/subject, sesji i jednorazowego nonce. Udana reautoryzacja zastępuje sesję. Klient AppAuth żąda `max_age=0`, claimu `auth_time` i używa PKCE. Testy w `tests/test_google_passkeys.py` i `__tests__/authMethods.test.ts`. | Rzeczywisty tenant Google i urządzenie iOS/Android nie były dostępne do E2E. Scenariusz ręczny: `SECURITY_REVIEW.md`. Ten podpunkt pozostaje niepotwierdzony integracyjnie. |
| R6 — klient sesji | `src/auth/session.ts` zachowuje refresh token po 429/503/błędzie sieci, stosuje `Retry-After`, naprawia kolejkę Keychain, ogranicza równoległe odświeżenia i odrzuca spóźnione odpowiedzi po logout. `__tests__/session.test.ts`. | Utrata odpowiedzi po rotacji na serwerze może wymagać ponownego logowania; wykrywanie replay pozostaje włączone. Brak testu na fizycznym urządzeniu. |
| R7 — konfiguracja produkcyjna | `app/config.py` normalizuje listy, odrzuca debug fingerprint/origin także w listach, sprawdza formaty. RP ID musi występować w trusted hosts i jako HTTPS origin; identyfikatory aplikacji mają walidację. `tests/test_config.py` sprawdza również pliki powiązań na hoście RP. | Zgodność z faktycznym podpisem aplikacji i publicznym TLS musi być sprawdzona podczas wdrożenia. |
| R8 — przypadki użycia | Przelew, wycena, wykonanie wymiany, MFA, passkeys i Google zostały rozdzielone na nazwane kroki usług w `app/services/`. Usługa posiada transakcję, helpery używają przekazanego połączenia. Testy finansowe, MFA i WebAuthn sprawdzają rollback, replay, role i współbieżność. | Część prostych odczytów oraz operacji auth nadal znajduje się w routerach; nie wykonano pełnego rozdzielenia każdego endpointu. |
| R9 — kontrakty i dokumentacja | `quote_id` jest UUID walidowanym na granicy API; kwoty i ID są ograniczone, także dla `bool`; wspólny limit salda w `app/money.py`. Poświadczenia są ukryte w `repr`. OpenAPI opisuje wycenę, transfer i idempotencję. `tests/test_schemas.py`, `tests/test_openapi_finance.py`. | Pełny opis wszystkich endpointów OpenAPI nie był celem tej iteracji; macierz ASVS wskazuje pozostałe luki dokumentacyjne. |
| R10 — uruchamianie | Skrypty Unix/Windows wybierają Python 3.11–3.13 i odrzucają niezgodny istniejący venv. `tests/test_start_scripts.py` sprawdza Unix w kontrolowanym środowisku; README opisuje odtworzenie venv. | Rzeczywiste uruchomienie Windows z samym 3.12/3.13 i launcherem mDNS/TLS nie było możliwe na tym macOS. |
| R11 — ASVS | `ASVS_5.0.0_L2_MATRIX.md` ocenia wszystkie 70 L1 + 183 L2 wymagania z przypiętego CSV. `tests/test_asvs_matrix.py` sprawdza hash źródła, kompletność identyfikatorów i oryginalnych opisów. `SECURITY_REVIEW.md` oddziela lokalne testy od urządzeń, dostawcy i wdrożenia. | Liczne pozycje pozostają częściowe, N/D, brakujące lub nieocenione. Macierz nie jest certyfikacją ani deklaracją pełnej zgodności L2. |
| R12 — bramki | Lokalnie przechodzą 222 testy backendu na Pythonie 3.11.0, 3.12.2 i 3.13.7; Ruff, mypy, 28 testów Jest i `tsc --noEmit`. Pełny `pip-audit` na niezmienionym lockfile: brak znanych podatności. | Brak wykonania CI dla tej lokalnej gałęzi oraz E2E na urządzeniu i z prawdziwym Google. |

## Co stało się prostsze

Routery finansowe kierują żądania do przypadków użycia. W usługach nazwy funkcji pokazują kolejność: kontrola aktualnej sesji, rozpoznanie ponowienia, walidacja kontekstu operacji, atomowe księgowanie oraz budowanie wyniku. Operacje danych przyjmują połączenie otwarte przez przypadek użycia, dzięki czemu granica `BEGIN IMMEDIATE` i wspólny commit sald, historii, księgi i audytu są widoczne. Integracje kursów NBP i OIDC są adapterami. W usługach passkeys i Google weryfikacja kryptograficzna odbywa się przed krótką transakcją zapisu, a stan i uprawnienia są ponownie sprawdzane pod blokadą.

## Migracje i aktualizacja klienta

- Migracja 0015 zachowuje zastosowane 0010–0014 i dane finansowe; dodaje jawny stan pochodzenia hasła dla kont historycznych. Przed aktualizacją wykonaj kopię bazy i używaj tego samego `MFA_ENCRYPTION_KEY`.
- Zmiana modelu sesji z migracji 0013 wymaga jednorazowego ponownego logowania; stare sesje nie mają refresh tokenu. Klient czyści dawny pojedynczy token z Keychain.
- `POST /api/auth/google/reauth` zwraca obecnie `AuthResponse` z nową parą tokenów zamiast 204. Klient z tej gałęzi zapisuje parę; backend i frontend należy aktualizować razem.
- Skrypty startowe odrzucają venv z niewspieranym Pythonem; README opisuje jego odtworzenie bez usuwania bazy.

## Wykonane kontrole

W katalogu `backend`:

```sh
python -m pytest -q
ruff check app tests launcher.py
ruff format --check app tests launcher.py
mypy app
pip-audit -r requirements.lock.txt
```

`pytest`: 222 passed na Pythonie 3.11.0, 3.12.2 i 3.13.7 po ostatnim teście finansowym 413. Ruff i mypy: zaliczone na Pythonie 3.12.2. `pip-audit` uruchomiono z lokalnym `--cache-dir`, ale z pełnym rozwiązywaniem zależności; wynik: `No known vulnerabilities found`. Nie jest to gwarancja braku nieznanych podatności.

W katalogu głównym: `npm test -- --runInBand` — 28 passed; `tsc --noEmit` — zaliczone. W izolowanym worktree użyto `node_modules` istniejącego głównego checkoutu, bez modyfikowania tamtego drzewa.

Workflow `.github/workflows/backend.yml` deklaruje macierz 3.11/3.12/3.13, ale nie ma uruchomienia dla lokalnych commitów. Kontrola Windows, realnego TLS/mDNS, passkeys na urządzeniu, Google i NBP pozostaje osobna. Weryfikacja podpisu OIDC/WebAuthn w testach używa kontrolowanych lokalnych kluczy i prawdziwych funkcji kryptograficznych; nie dowodzi działania dostawcy ani platformy mobilnej.

## Pozostałe decyzje wdrożeniowe

Przed publicznym wdrożeniem trzeba potwierdzić rzeczywisty przepływ Google `auth_time` i natywne passkeys na obu platformach, uruchomić CI na tym SHA, sprawdzić TLS i pliki powiązań pod publiczną domeną, ustalić retencję/centralizację logów, szyfrowanie SQLite w spoczynku oraz zarządzanie i rotację klucza MFA. Braki te są jawnie oznaczone w macierzy ASVS i nie blokują lokalnego MVP na fikcyjnych danych, ale nie pozwalają ogłaszać pełnej zgodności ASVS L2 ani gotowości do przechowywania prawdziwych danych finansowych.
