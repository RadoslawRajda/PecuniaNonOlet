# Backend PecuniaNonOlet

Backend FastAPI z rejestracją, logowaniem i wylogowaniem. Konta oraz sesje są przechowywane w SQLite, a schemat bazy jest zarządzany przez Alembic. Skrypt uruchamia API i ogłasza je w sieci lokalnej przez mDNS.

## Wymagania

- Python 3.11 lub nowszy
- Komputer i telefon w tej samej sieci lokalnej

## Uruchomienie

W katalogu `backend/`:

**Windows:** uruchom `start-windows.bat` (można przez dwuklik).

**macOS / Linux:**

```sh
./start-unix.sh
```

Skrypt tworzy środowisko `.venv`, instaluje biblioteki, wybiera adres IP, przygotowuje lokalny certyfikat TLS i uruchamia FastAPI po HTTPS na porcie 8000. Przy starcie backend automatycznie wykonuje oczekujące migracje Alembic. Jeśli komputer ma kilka adresów, poprosi o wybór. Adres można podać ręcznie:

```sh
./start-unix.sh --ip 192.168.1.45
```

Na Windows: `start-windows.bat --ip 192.168.1.45`.

Po starcie API jest dostępne pod `https://pecunianonolet.local:8000/` oraz `https://<adres-LAN>:8000/`. Usługa mDNS `_pecunianonolet._tcp.local.` ogłasza port TLS i właściwość `scheme=https`. Dodatkowy port `8001` wystawia po HTTP wyłącznie stronę instalacji CA (`/`) i publiczny plik CA (`/local-root-ca.cer`); pozostałe ścieżki HTTP zwracają 404. Po instalacji CA używaj HTTPS na porcie 8000.

Ponieważ publiczne urzędy certyfikacji nie wystawiają zaufanych certyfikatów dla nazw `.local`, launcher tworzy lokalny prywatny CA i certyfikat serwera z SAN dla `pecunianonolet.local` i aktualnego adresu LAN. Certyfikaty i klucze są przechowywane w `backend/data/tls/` (katalog jest pomijany przez Git); klucze prywatne mają uprawnienia tylko dla użytkownika na macOS/Linux. Przy pierwszym uruchomieniu terminal pokaże ścieżkę do `local-root-ca.cer` i odcisk SHA-256.

Najprostsza konfiguracja telefonu: podłącz telefon i komputer do tej samej zaufanej sieci Wi-Fi, otwórz `http://<adres-LAN-komputera>:8001/` na telefonie i pobierz **publiczny** plik CA. Strona pokazuje instrukcję instalacji oraz odcisk SHA-256; porównaj go z wartością wyświetloną w terminalu komputera przed zaufaniem certyfikatowi. HTTP służy tu wyłącznie do dostarczenia publicznego pliku CA i instrukcji, więc nie wpisuj tam haseł ani innych danych konta. Nie instaluj certyfikatu, jeśli odciski się różnią.

- **iPhone:** po pobraniu profilu wejdź w `Ustawienia > Ogólne > VPN i urządzenia zarządzane`, wybierz pobrany profil i zainstaluj go. Następnie przejdź do `Ustawienia > Ogólne > To urządzenie... > Ustawienia zaufania certyfikatów` i włącz pełne zaufanie dla tego CA. Sama instalacja profilu nie włącza zaufania TLS.
- **Android:** zainstaluj plik jako certyfikat CA w ustawieniach zabezpieczeń systemu. Konfiguracja aplikacji Android dopuszcza certyfikaty dodane przez użytkownika wyłącznie dla `pecunianonolet.local`; pozostałe domeny zachowują systemowy zestaw zaufanych CA.

Lokalny CA jest przeznaczony do developmentu w zaufanej sieci. Jeśli usuniesz `backend/data/tls/local-root-ca-key.pem` albo cały katalog `tls`, launcher utworzy nowy CA i trzeba będzie ponownie zainstalować jego certyfikat na telefonach. Nie używaj tego CA do publicznego wdrożenia.

Po instalacji certyfikatu korzystaj z backendu przez HTTPS:

- Aplikacja/API: `https://pecunianonolet.local:8000/`
- Domena mDNS: `pecunianonolet.local`
- Swagger UI: `https://pecunianonolet.local:8000/docs`
- OpenAPI JSON: `https://pecunianonolet.local:8000/openapi.json`

Naciśnij `Ctrl+C`, aby zatrzymać API i mDNS. Zamknięcie okna skryptu kończy proces serwera. Baza pozostaje w `data/pecunia.db`. Migracje można też uruchomić ręcznie z katalogu `backend/`:

```sh
DATABASE_PATH=data/pecunia.db .venv/bin/alembic -c alembic.ini upgrade head
```

Na Windows użyj `.venv\Scripts\alembic.exe -c alembic.ini upgrade head`.

Konfiguracja jest odczytywana przy starcie instancji. Wartość podana jawnie przez
`create_app(Settings(...))` ma pierwszeństwo przed zmiennymi środowiskowymi, a te
przed `backend/.env` i wartościami domyślnymi. Migracje uruchomione ręcznie przez
Alembic używają tej samej konfiguracji env/`.env`; żądania, limiter i rejestr
zdarzeń bezpieczeństwa korzystają z konfiguracji własnej instancji aplikacji.

## Struktura backendu

`app/main.py` składa aplikację FastAPI i middleware. Routery w `app/routes/` obsługują HTTP i walidację wejścia; operacje finansowe zmieniające stan są wykonywane przez serwisy z `app/services/`, które obejmują zapis sald, księgi i audytu jedną transakcją SQLite. Integracje zewnętrzne, takie jak NBP, Google OIDC i Turnstile, są w `app/adapters/`. Ustawienia pochodzą z `app/config.py`; migracje Alembic są samodzielną historią schematu i nie importują modeli aplikacji. Część zapytań odczytowych i logiki uwierzytelniania nadal znajduje się w routerach.

## Endpointy

| Metoda | Ścieżka | Działanie |
| --- | --- | --- |
| `POST` | `/api/register` | Rejestracja, utworzenie rachunków walutowych i wydanie tokenu |
| `POST` | `/api/login` | Logowanie i wydanie tokenu |
| `POST` | `/api/refresh` | Atomowa rotacja access i refresh tokenu |
| `GET` | `/api/mfa` | Status MFA zalogowanego użytkownika |
| `POST` | `/api/mfa/totp/setup` | Rozpoczęcie konfiguracji aplikacji TOTP |
| `POST` | `/api/mfa/totp/confirm` | Potwierdzenie kodu i aktywacja TOTP; zwraca kody odzyskiwania raz |
| `POST` | `/api/login/mfa` | Drugi etap logowania kodem TOTP lub kodem odzyskiwania |
| `POST` | `/api/mfa/totp/disable` | Wyłączenie TOTP po ponownym podaniu hasła i kodu |
| `GET` | `/api/me` | Dane zalogowanego użytkownika |
| `GET` | `/api/accounts` | Rachunki i osobne salda zalogowanego użytkownika |
| `GET` | `/api/transactions` | Stronicowana historia operacji użytkownika |
| `GET` | `/api/transactions/{transaction_id}` | Szczegóły transakcji widocznej dla użytkownika |
| `POST` | `/api/transfers` | Przelew do użytkownika wskazanego adresem e-mail |
| `GET` | `/api/exchange-rates` | Aktualne kursy walut z tabeli A NBP |
| `POST` | `/api/exchange/quote` | Wycena wymiany ważna przez 120 sekund |
| `POST` | `/api/exchange` | Atomowa wymiana między rachunkami użytkownika |
| `PUT` | `/api/profile/photo` | Ustawienie zdjęcia profilowego użytkownika |
| `GET` | `/api/profile/photo` | Pobranie własnego zdjęcia profilowego |
| `DELETE` | `/api/profile/photo` | Usunięcie własnego zdjęcia profilowego |
| `GET` | `/api/analytics/overview` | Zbiorcze statystyki użytkowników i transakcji (rola `analyst`) |
| `GET` | `/api/analytics/users` | Stronicowana lista użytkowników i liczba ich rachunków oraz operacji (rola `analyst`) |
| `GET` | `/api/analytics/transactions` | Stronicowana lista transakcji z filtrami (rola `analyst`) |
| `GET` | `/api/analytics/audit-events` | Stronicowany dziennik operacji finansowych i administracyjnych (rola `analyst`) |
| `POST` | `/api/logout` | Unieważnienie tokenu |
| `POST` | `/api/change-password` | Zmiana hasła i unieważnienie wszystkich sesji użytkownika |
| `POST` | `/api/auth/google/nonce` | Jednorazowy nonce do logowania Google OIDC |
| `POST` | `/api/auth/google/login` | Weryfikacja Google ID tokenu i wydanie lokalnej sesji |
| `POST` | `/api/auth/google/link/nonce` | Nonce do jawnego połączenia Google z zalogowanym kontem |
| `POST` | `/api/auth/google/link` | Połączenie kont po świeżym uwierzytelnieniu |
| `POST` | `/api/auth/google/reauth/nonce` | Wyzwanie do ponownego potwierdzenia Google w bieżącej sesji |
| `POST` | `/api/auth/google/reauth` | Sprawdzenie świeżego Google `auth_time` i odnowienie kontekstu uwierzytelnienia |
| `GET` | `/api/passkeys` | Lista własnych passkeys bez ujawniania kluczy publicznych |
| `POST` | `/api/passkeys/registration/options` | Początek rejestracji passkey |
| `POST` | `/api/passkeys/registration/verify` | Weryfikacja attestation i zapis poświadczenia |
| `POST` | `/api/passkeys/authentication/options` | Jednorazowe wyzwanie do logowania passkey |
| `POST` | `/api/passkeys/authentication/verify` | Weryfikacja assertion i wydanie lokalnej sesji |
| `DELETE` | `/api/passkeys/{credential_id}` | Usunięcie własnej passkey |
| `GET` | `/.well-known/apple-app-site-association` | Powiązanie domeny z iOS dla passkeys |
| `GET` | `/.well-known/assetlinks.json` | Powiązanie domeny z Androidem dla passkeys |

Rejestracja przyjmuje JSON `{"email":"test@example.com","password":"haslo1234","captcha_token":"..."}`. Token CAPTCHA pochodzi z obowiązkowego widżetu Cloudflare Turnstile w aplikacji i jest weryfikowany przez backend przed utworzeniem konta. Logowanie przyjmuje e-mail i hasło. Hasło przy rejestracji musi mieć od 8 do 128 znaków. Odpowiedź udanej rejestracji lub logowania zawiera `user`, `access_token`, `refresh_token`, `token_type`, `expires_in` i `refresh_expires_in`. Access token jest losowym tokenem opaque ważnym 15 minut; refresh token jest ważny do 30 dni bezczynności, a sesja ma limit bezwzględny 90 dni. W bazie przechowywane są wyłącznie hashe tokenów. Aplikacja mobilna zapisuje oba tokeny w Keychain/Keystore, wysyła access token w `Authorization: Bearer <access_token>` i po odpowiedzi 401 wykonuje pojedyncze współdzielone odświeżenie.

Odświeżanie: `POST /api/refresh` z JSON `{"refresh_token":"..."}` zwraca nową parę. Każde odświeżenie unieważnia poprzednią parę. Ponowne użycie zużytego refresh tokenu unieważnia całą rodzinę sesji. Wylogowanie: `POST /api/logout` z JSON `{"refresh_token":"..."}` unieważnia sesję bez potrzeby ważnego access tokenu. Zmiana hasła, włączenie/wyłączenie MFA oraz wykrycie ponownego użycia refresh tokenu unieważniają aktywne sesje. Jedno konto może mieć maksymalnie pięć aktywnych sesji; utworzenie kolejnej unieważnia najstarszą. Migracja do nowego modelu wymaga jednorazowego ponownego logowania; zachowuje konta i dane finansowe, ale unieważnia dotychczasowe sesje.

Klient zachowuje tokeny przy 429, 503, błędzie sieci i timeoutcie odświeżania,
uwzględnia `Retry-After` (maksymalnie 60 sekund) i nie wysyła równoległych
żądań rotacji dla jednej sesji. Potwierdzone 401 lub niepoprawna odpowiedź 200
kończy sesję lokalną. Jeśli serwer wykonał rotację, ale odpowiedź zginęła w sieci,
klient nie może odzyskać nowego refresh tokenu: kolejna próba starym tokenem
zostanie potraktowana jako replay, a użytkownik zaloguje się ponownie.

Migracja 0015 oznacza stare konta połączone z Google jako konta o nieustalonym
pochodzeniu hasła. Nie usuwa ich hashy ani metod MFA. Użytkownik, który nie zna
historycznego hasła, może ustanowić nowe przez `POST /api/change-password` bez
`current_password` albo rozpocząć konfigurację TOTP po świeżym logowaniu Google
(nie starszym niż 5 minut). Podanie błędnego starego hasła nadal kończy się 401.
Po ustawieniu nowego hasła konto przechodzi na zwykłą politykę hasła lokalnego.

Gdy użytkownik ma włączone MFA, `/api/login` zamiast tokenów zwraca `mfa_required: true`, `challenge_token` i `expires_in`. Frontend kończy logowanie przez `POST /api/login/mfa`, który wydaje parę access/refresh. Szczegółowy przepływ konfiguracji, przykładowe żądania i odpowiedzi opisuje [dokumentacja MFA TOTP](docs/TOTP_MFA.md).

## Google OIDC i passkeys — lokalny development

Backend wczytuje `backend/.env`; aplikacja React Native wczytuje główny `.env`. Skopiuj odpowiednie pliki `.env.example` i wpisz identyfikatory klientów OAuth z jednego projektu Google Cloud. Włącz w nim Google Identity/OAuth, utwórz klienta iOS dla `com.rajda.pecunianonolet` oraz klienta Android dla `com.pecunianonolet` i odcisku debugowego SHA-256 z pliku `android/app/debug.keystore`. Identyfikatory klientów są publiczne — nie dodawaj do aplikacji `client_secret`.

W `backend/.env` ustaw `GOOGLE_OAUTH_CLIENT_IDS` jako listę identyfikatorów rozdzielonych przecinkami. W głównym `.env` ustaw `GOOGLE_IOS_CLIENT_ID` i `GOOGLE_ANDROID_CLIENT_ID`. W `ios/PecuniaNonOlet/Info.plist` zastąp `REPLACE_WITH_IOS_CLIENT_ID_PREFIX`, a w `android/app/build.gradle` zastąp `REPLACE_WITH_ANDROID_CLIENT_ID_PREFIX`. Wartość prefiksu to identyfikator klienta bez końcówki `.apps.googleusercontent.com`; np. `123-example.apps.googleusercontent.com` daje schemat `com.googleusercontent.apps.123-example`. Redirect jest obsługiwany przez systemową przeglądarkę i AppAuth (Authorization Code + PKCE). Backend przyjmuje ID token, sprawdza podpis, `iss`, `aud`, `azp`, `exp`, `sub` i jednorazowy `nonce`. Token dostępu Google nie jest przechowywany jako sesja aplikacji. Istniejące konta nie są automatycznie łączone po samym adresie e-mail.

Passkeys używają `py_webauthn` i natywnego menedżera poświadczeń iOS/Android. Backend wymaga świeżego dowodu logowania (do 5 minut) przed dodaniem/usunięciem passkey i wymusza resident credential oraz User Verification. Dla logowania weryfikuje jednorazowy challenge, dozwolony origin, RP ID, podpis, User Verification i `userHandle`; TOTP pozostaje wymagane, jeśli jest włączone. `signCount` jest przekazywany verifierowi i aktualizowany po assertion, ale backend nie wymusza wzrostu licznika: wartość zero i powtarzające się zero są prawidłowe dla synchronizowanych passkeys. Aplikacja nie podejmuje decyzji dostępu na podstawie flag BE/BS ani ich nie utrwala. Sesja zapisuje metodę, którą została uwierzytelniona. Google `auth_time` jest przechowywane osobno od czasu utworzenia sesji; bez świeżego `auth_time` sesja Google nie może autoryzować zmiany metod bezpieczeństwa.

Natywny request Google zawiera żądanie claimu `auth_time`. W ustawieniach klienta Google OAuth włącz dodatkowe claimy `auth_time`; Google może go nie zwrócić, jeśli nie jest dostępny dla konfiguracji projektu. Zwykłe logowanie może wtedy nadal działać, ale operacja wymagająca świeżej reautoryzacji zostanie odrzucona. Użytkownik musi ponownie uwierzytelnić konto Google, a nie tylko odświeżyć lokalną sesję.

Żądania logowania, rejestracji, Google, passkeys, MFA, wymiany kursów, wycen i operacji finansowych są ograniczane trwałymi licznikami SQLite. Dodatkowe limity body wynoszą 10 KiB dla Google, 16 KiB dla pozostałych żądań uwierzytelniania, 32 KiB dla passkeys, 2 MiB + narzut dla zdjęcia i 1 MiB dla pozostałych żądań. Limity IP używają adresu peer połączenia ASGI; nagłówki `X-Forwarded-For` są ignorowane. Przy proxy należy skonfigurować zaufanie na warstwie serwera i nie przekazywać niezweryfikowanych nagłówków jako adresu klienta.

Dla `pecunianonolet.local` backend serwuje wymagane pliki powiązań z domyślnym Apple Team ID, identyfikatorem aplikacji oraz fingerprintem debugowego Androida z tego repozytorium. Są to ustawienia developerskie i można je nadpisać zmiennymi `APPLE_TEAM_ID`, `IOS_BUNDLE_ID`, `ANDROID_PACKAGE_NAME` i `ANDROID_SHA256_CERT_FINGERPRINTS`. Lista `WEBAUTHN_ALLOWED_ORIGINS` domyślnie dopuszcza lokalny HTTPS w przeglądarce, natywny origin iOS oraz certyfikat Android debug; dla innej domeny lub podpisu ustaw własną listę. Nie dodawaj `Origin` z żądania klienta do tej listy.

Na iPhonie zainstaluj aplikację developerską podpisaną tym samym Apple Team ID, włącz w Ustawieniach tryb developerski oraz `Associated Domains Development`, a następnie uruchom aplikację ponownie. Entitlement testowy zawiera `webcredentials:pecunianonolet.local?mode=developer`. Wpisuje się samą domenę, bez portu. Zgodnie z [dokumentacją Apple](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.associated-domains) tryb developer pozwala urządzeniu pobrać AASA bezpośrednio z prywatnej domeny zamiast korzystać z publicznego CDN Apple. AASA musi być dostępny przez HTTPS na standardowym porcie 443; API i Swagger nadal działają na porcie 8000.

Aby uruchomić ograniczony serwer AASA i Android Asset Links na porcie 443, pozostaw zwykły backend uruchomiony, otwórz drugie okno terminala i uruchom z katalogu `backend`:

```sh
sudo .venv/bin/python launcher.py --aasa-only --ip <LAN_IP>
```

Podaj ten sam lokalny adres IPv4 co przy starcie backendu. Ten tryb wymaga uprawnień do portu 443 i wystawia wyłącznie dwa pliki powiązań; pozostałe ścieżki zwracają 404. Zatrzymaj go przez `Ctrl+C`. W Windows uruchom terminal jako administrator i użyj `.venv\\Scripts\\python.exe launcher.py --aasa-only --ip <LAN_IP>`. Lokalny serwer musi mieć certyfikat TLS zaufany przez telefon, a nazwa `.local` musi rozwiązywać się na iPhonie. Sprawdź odpowiedzi:

```text
https://pecunianonolet.local/.well-known/apple-app-site-association
https://pecunianonolet.local/.well-known/assetlinks.json
```

Passkeys pod `.local` są wyłącznie testowe. Testują natywny przepływ iOS tylko przy uruchomieniu aplikacji developerskiej z prawidłowym entitlementem i włączonym trybem Associated Domains developer na telefonie; sam działający HTTPS w Safari tego nie konfiguruje. Produkcja wymaga publicznej domeny z prawidłowym certyfikatem, właściwym Apple Associated Domains oraz fingerprintem certyfikatu używanego do podpisania aplikacji. Nie publikuj debugowego fingerprintu jako konfiguracji produkcyjnej.

Przy pierwszej konfiguracji skopiuj `backend/.env.example` do `backend/.env`. Typowane ustawienia Pydantic wczytują ten plik przy starcie. `APP_ENV` przyjmuje `development`, `test` lub `production`; domyślna konfiguracja jest przeznaczona wyłącznie do lokalnego developmentu. Dla produkcji ustaw jawne `TRUSTED_HOSTS` (nazwy hostów API bez wildcardów). Produkcyjny profil wyłącza publiczne `/docs`, `/redoc` i `/openapi.json` oraz odrzuca nieznane nagłówki Host. Walidacja blokuje także testowy sekret Turnstile, `.local` RP ID i debugowy fingerprint Androida. Wygeneruj klucz poleceniem `.venv/bin/python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` (Windows: `.venv\\Scripts\\python.exe -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`) i wklej wynik jako `MFA_ENCRYPTION_KEY`. Wartość `TURNSTILE_SECRET_KEY` w przykładzie jest publicznym kluczem testowym Cloudflare i służy wyłącznie do lokalnego developmentu; przed wdrożeniem skonfiguruj własną parę kluczy Turnstile. Możesz opcjonalnie ustawić `TURNSTILE_EXPECTED_HOSTNAME`. Po zmianie `.env` uruchom backend ponownie. Zachowaj ten sam klucz MFA po każdym restarcie, poza repozytorium. To klucz szyfrujący sekrety TOTP w bazie i nie jest tym samym co lokalny CA TLS. Zmiana klucza po włączeniu MFA uniemożliwi odszyfrowanie dotychczas zapisanych sekretów.

Frontend konfiguruje publiczny `TURNSTILE_SITE_KEY` w głównym pliku `.env` na podstawie `.env.example`. Przykład używa klucza testowego wymuszającego interakcję; klucze testowe nie chronią przed botami. Do produkcji utwórz własny widżet Turnstile i ustaw jego klucz publiczny we frontendzie oraz odpowiadający mu sekret w `backend/.env`.

Nowe konta otrzymują rolę `user`, której nie można wybrać w żądaniu rejestracji. Konto `analyst` może utworzyć zaufany lokalny administrator po migracji bazy:

```sh
.venv/bin/python -m app.admin create-analyst analityk@example.com
```

Hasło jest wpisywane interaktywnie i nie trafia do argumentów procesu. Pole `user.role` jest zwracane przez logowanie, rejestrację i `/api/me`.

Endpointy analityczne wymagają tokenu konta `analyst`. Lista użytkowników przyjmuje `limit` (1–100), `offset` oraz opcjonalne `role`. Lista transakcji przyjmuje `limit`, `offset`, `kind`, `status`, `user_id` oraz zakres czasu `from` i `to` jako znaczniki czasu Unix. Każda odpowiedź analityczna wykonuje powiązane odczyty w jednej transakcji SQLite, więc liczniki i rekordy pochodzą z tego samego snapshotu. Odpowiedzi zawierają wyłącznie dane potrzebne do analizy; nie zwracają hashy haseł ani tokenów sesji.

Dziennik audytu zawiera informacje o transakcjach otwarcia, przelewach, wymianach oraz utworzeniu konta analityka przez lokalnego administratora. Wpis jest zapisywany w tej samej transakcji SQLite co operacja, której dotyczy. Wpisy są tylko dopisywane; aktualizacja lub usunięcie jest blokowane przez bazę. Migracja uzupełnia podstawowe wpisy dla wcześniejszych transakcji. Odczyt dziennika jest dostępny wyłącznie dla roli `analyst`; rekordy nie zawierają haseł ani tokenów.

Zmiana hasła wymaga nagłówka `Authorization: Bearer <token>` oraz JSON `{"current_password":"stare","new_password":"nowe-haslo"}`. Sukces zwraca `reauthentication_required: true`; użytkownik musi zalogować się ponownie.

Rejestracja tworzy osobne rachunki PLN, EUR, USD, GBP i CZK. Rachunek PLN otrzymuje jednorazowe saldo początkowe 1000,00 PLN, zapisane jako transakcja otwarcia i wpis księgowy; pozostałe rachunki rozpoczynają z saldem 0,00. Migracja Alembic uzupełnia rachunki istniejących użytkowników bez resetowania sald.

Lista historii przyjmuje `limit` (1–100, domyślnie 20) i `offset` (domyślnie 0), sortuje wpisy deterministycznie od najnowszych. Kwoty są zwracane jako całkowita liczba najmniejszych jednostek oraz tekst dziesiętny; wymiany zawierają obie kwoty i utrwalony kurs. Dostęp do historii jest ograniczony do nadawcy lub odbiorcy danej operacji.

Przelew wymaga nagłówków `Authorization: Bearer <token>` i `Idempotency-Key` oraz JSON zawierającego `recipient_email`, `source_account_id`, `currency_code` i dodatnie `amount_minor`. Kwota jest pobierana i księgowana w tej samej walucie; brak środków na wybranym rachunku nie powoduje użycia innego rachunku. Ponowienie tego samego żądania z tym samym kluczem zwraca poprzedni przelew bez ponownego księgowania; użycie klucza dla innej operacji kończy się konfliktem.

Kursy są pobierane z API NBP przez HTTPS. Tabela musi mieć datę nieprzyszłą i nie starszą niż 7 dni kalendarzowych; ten limit obejmuje weekendy i dni bez publikacji. Endpoint wyceny przyjmuje `source_account_id`, `destination_account_id` i `source_amount_minor`; zwraca kwotę docelową, kurs krzyżowy do prezentacji, dokładne kursy źródłowy i docelowy względem PLN, datę i numer tabeli NBP oraz termin ważności wyceny. Oba dokładne kursy wejściowe i identyfikator tabeli są utrwalane w rekordzie wyceny; pole `exchange_rate` jest przybliżonym kursem prezentacyjnym, nie podstawą księgowania. Kwota jest obliczana dokładnie z dziesiętnych kursów źródłowych jako liczba wymierna, a dopiero wynik w najmniejszych jednostkach jest zaokrąglany w dół. Ułamek poniżej najmniejszej jednostki nie jest osobno księgowany; wynik mniejszy od jednej jednostki jest odrzucany. Realizacja przyjmuje `quote_id` i nagłówek `Idempotency-Key`; kursu podanego przez klienta backend nie przyjmuje.

Zdjęcie przesyłaj jako `multipart/form-data` w wymaganym polu `file` na `PUT /api/profile/photo`; kontrakt pliku i odpowiedzi błędów jest dostępny w `/openapi.json` i Swagger UI. Backend dopuszcza JPEG, PNG i WebP do 2 MiB, sprawdza format na podstawie zawartości, odrzuca animacje i obrazy o nadmiernych wymiarach, a zapisuje przetworzony JPEG bez metadanych EXIF. Pliki przechowywane są poza katalogiem publicznym, pod losową nazwą; pobranie i usunięcie wymagają aktywnej sesji właściciela. Katalog można zmienić zmienną `PROFILE_PHOTO_DIR`; domyślnie znajduje się obok pliku bazy danych.

## Testy

Start scripts install exact runtime dependencies from `requirements-runtime.lock.txt`. Direct ranges are kept in `requirements.txt`; the lockfile records the validated resolution. CI and local test runs use `requirements.lock.txt`, which pins runtime and development dependencies.

```sh
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m pytest -q
```

Na Windows użyj `.venv\Scripts\python.exe` zamiast `.venv/bin/python`.

Hasła są zapisywane jako hashe Argon2. Rejestracja i zmiana hasła odrzucają lokalnie sprawdzane popularne hasła z pierwszych 3000 wpisów listy SecLists oraz kontekstowe nazwy `Pecunia`, `PecuniaNonOlet`, `nonolet`, domenę lokalną, rolę `analyst` i identyfikator z adresu e-mail. Hasła nie są wysyłane do zewnętrznego sprawdzacza. Lista znajduje się w `app/resources/common-passwords.txt`; jej źródło i licencja są w `app/resources/SECLists-LICENSE.txt`. Odświeżenie listy powinno aktualizować ten plik i testy wraz z datą/commitem źródła.

W bazie przechowywane są tylko hashe tokenów i kodów MFA. Tabela `security_events` dopisuje zdarzenia logowania, rejestracji, sesji, zmian metod uwierzytelniania i odmów autoryzacji. Zdarzenia zawierają typ, wynik, metodę, ścieżkę szablonu endpointu, wewnętrzne ID użytkownika i czas Unix UTC; nie zapisują haseł, tokenów, kodów, e-maili ani body. Triggery blokują aktualizację i usuwanie rekordów. Log znajduje się w tej samej bazie SQLite i nie jest wysyłany do osobnego systemu, więc nie spełnia wymogu centralizacji/izolacji logów przed publicznym wdrożeniem; retencję trzeba określić i wdrożyć wraz z zewnętrznym odbiornikiem. Odpowiedzi API mają `Cache-Control: no-store`. Odpowiedzi HTTP mają CSP, `X-Content-Type-Options`, `Referrer-Policy` i politykę blokującą osadzanie; HSTS jest dodawany tylko do odpowiedzi HTTPS. Swagger w development ma osobną, luźniejszą CSP ze względu na osadzony bootstrap FastAPI i zasoby jsDelivr; Swagger jest wyłączony w profilu production. Próby kodów MFA są limitowane per konto. Połączenie lokalne korzysta z HTTPS z prywatnym CA, który użytkownik musi jawnie zainstalować i zweryfikować na telefonie. Backend nadal jest demonstracyjny, nie do publicznego wdrożenia; przed wdrożeniem wymagane są publicznie zaufany TLS, system zarządzania sekretami, monitorowanie/audyt centralny i pełna ocena ASVS.
