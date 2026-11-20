# MFA TOTP — dokumentacja integracji

TOTP jest dodatkowym wymaganym krokiem po zalogowaniu metodą hasła, Google lub passkey, gdy użytkownik wcześniej je włączył. Żadna z tych metod logowania nie omija aktywnego MFA. Dostępne są jednorazowe kody odzyskiwania.

## Konfiguracja serwera

Do szyfrowania sekretów TOTP backend wymaga stabilnego klucza AES-256. Wygeneruj go lokalnie:

```sh
python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Skopiuj `backend/.env.example` do `backend/.env` i wpisz wygenerowany wynik jako `MFA_ENCRYPTION_KEY`. Launcher automatycznie wczytuje ten plik; po jego zmianie uruchom backend ponownie. Nie dodawaj prawdziwego klucza do repozytorium, aplikacji mobilnej, logów ani bazy SQLite. Utrata klucza uniemożliwi odszyfrowanie aktywnych sekretów; przywróć go z bezpiecznej kopii. Pierwszy krok `/api/login` nie odszyfrowuje sekretu: może zwrócić challenge, ale bez poprawnego klucza drugi krok TOTP kończy się `503` i nie wydaje tokenu. Brak albo błędny klucz nie powoduje fallbacku do logowania samym hasłem. Migracja `0008_totp_mfa` uruchamia się automatycznie przy starcie aplikacji.

Launcher uruchamia API przez HTTPS. Dla nazwy mDNS `.local` generuje prywatny CA i certyfikat z SAN dla `pecunianonolet.local`; publiczny CA nie może wystawić zaufanego certyfikatu dla takiej nazwy. Certyfikat CA znajduje się w `backend/data/tls/local-root-ca.cer`, a fingerprint SHA-256 jest wypisywany w terminalu. Przed użyciem aplikacji mobilnej zainstaluj ten CA na telefonie i porównaj fingerprint niezależnym kanałem. iOS wymaga ręcznego włączenia pełnego zaufania dla zainstalowanego root CA; Android ufa certyfikatom użytkownika w aplikacji tylko dla `pecunianonolet.local`. Lokalny CA chroni transport w kontrolowanym środowisku, ale nie jest CA publicznym ani rozwiązaniem do publicznego wdrożenia.

## Kontrakt API

Chronione endpointy wymagają `Authorization: Bearer <token>`. Wszystkie odpowiedzi `/api/` mają `Cache-Control: no-store`. Schemat OpenAPI jest dostępny pod `/openapi.json`, a Swagger UI pod `/docs`.

### Odczyt statusu

`GET /api/mfa`

```json
{"totp_enabled": false}
```

### Rozpoczęcie konfiguracji

`POST /api/mfa/totp/setup` z aktywną sesją. Dla konta z hasłem lokalnym wymagane jest aktualne hasło:

```json
{"current_password":"obecne-haslo"}
```

Dla konta Google-only bez hasła lokalnego wyślij `{}`. Wtedy backend wymaga świeżego uwierzytelnienia Google (`auth_time` nie starsze niż 5 minut). Identyczna reguła dotyczy wyłączenia TOTP i ustawienia pierwszego hasła.

Odpowiedź `200` zawiera sekret i URI do wygenerowania QR w aplikacji:

```json
{
  "secret":"BASE32SECRET...",
  "provisioning_uri":"otpauth://totp/…",
  "expires_at":1790000000
}
```

Sekret jest pokazany tylko w tej odpowiedzi, przechowywany w bazie w postaci AES-GCM i wygasa po 10 minutach. Frontend powinien umożliwić zeskanowanie QR lub ręczne wpisanie sekretu. Nie zapisuj sekretu w AsyncStorage ani logach.

Dla konta z hasłem lokalnym wymagane jest aktualne hasło. Konto Google-only bez hasła lokalnego przekazuje `{}`; backend wymaga wtedy świeżego uwierzytelnienia Google (`auth_time` nie starsze niż 5 minut). Identyczna reguła dotyczy wyłączenia TOTP i ustawienia pierwszego hasła.

### Potwierdzenie i aktywacja

`POST /api/mfa/totp/confirm` z tą samą sesją:

```json
{"code":"123456"}
```

Poprawna odpowiedź `200`:

```json
{
  "totp_enabled":true,
  "recovery_codes":["..."],
  "reauthentication_required":true
}
```

Pokaż kody odzyskiwania użytkownikowi tylko teraz i poproś, by zapisał je poza aplikacją. Backend przechowuje wyłącznie ich hashe. Aktywacja unieważnia wszystkie istniejące sesje, więc frontend powinien usunąć lokalny token i przejść do logowania.

### Logowanie

Pierwszy krok pozostaje `POST /api/login`:

```json
{"email":"user@example.com","password":"haslo"}
```

Konto bez MFA otrzymuje `access_token` oraz `refresh_token`. Access token jest ważny 15 minut; refresh token wygasa po 30 dniach bezczynności i maksymalnie po 90 dniach od utworzenia sesji. `POST /api/refresh` rotuje oba tokeny. Konto z MFA dostaje najpierw odpowiedź bez tokenów:

```json
{
  "mfa_required":true,
  "challenge_token":"…",
  "expires_in":300
}
```

Frontend powinien rozróżniać te odpowiedzi po polu `mfa_required`. W drugim przypadku przechowaj challenge tylko na czas logowania i pokaż ekran kodu MFA. Wyślij kod z Authenticatora albo kod odzyskiwania:

`POST /api/login/mfa`

```json
{"challenge_token":"…","code":"123456"}
```

albo:

```json
{"challenge_token":"…","code":"RECOVERY_CODE"}
```

Kod TOTP ma 6 cyfr. Nowe kody odzyskiwania mają 22 znaki URL-safe (128 bitów entropii); kody wydane starszą wersją o długości 16 znaków pozostają obsługiwane. Sukces zwraca tę samą odpowiedź sesji co zwykłe logowanie: `access_token`, `refresh_token`, `expires_in`, `refresh_expires_in` i `user`. Access token jest ważny 15 minut, a refresh token 30 dni bezczynności i maksymalnie 90 dni od utworzenia sesji; `POST /api/refresh` rotuje oba tokeny. Challenge jest jednorazowy i wygasa po 5 minutach. Ponowne użycie challenge, TOTP z już zaakceptowanego kroku lub odzyskanego kodu kończy się `401`.

### Wyłączenie

`POST /api/mfa/totp/disable` z aktywną sesją:

```json
{"current_password":"obecne-haslo","code":"123456"}
```

W polu `code` można przekazać TOTP lub jednorazowy kod odzyskiwania. Poprawna odpowiedź:

```json
{"totp_enabled":false,"reauthentication_required":true}
```

Wyłączenie wymaga ponownego hasła (albo świeżego uwierzytelnienia Google dla kont Google-only) oraz świeżego TOTP lub kodu odzyskiwania. Unieważnia wszystkie sesje i czyści challenge. Frontend usuwa oba tokeny i kieruje użytkownika do logowania.

## Błędy i ograniczenia prób

- `401` — błędne hasło/kod, nieważny challenge lub brak sesji.
- `409` — MFA już włączone, nie rozpoczęto konfiguracji albo konfiguracja wygasła; przy wygaśnięciu rozpocznij setup od nowa.
- `422` — niepoprawny format JSON lub kodu.
- `429` — pięć błędnych kodów w oknie 15 minut; konto MFA jest blokowane na 15 minut. Odpowiedź zawiera `Retry-After` w sekundach.
- `503` — brak albo nieprawidłowy `MFA_ENCRYPTION_KEY` lub problem z dostępnością bazy.

Limity są egzekwowane per konto w bazie, także przy tworzeniu nowych challenge. UI powinien zachować challenge po błędnym kodzie, dopóki nie wygaśnie, i respektować `Retry-After` przy `429`.

## Reguły implementacji

- Sekret TOTP: losowy Base32, 160 bitów; szyfrowanie AES-GCM 256 bitów z nonce per zapis i AAD powiązanym z użytkownikiem oraz przeznaczeniem.
- TOTP: SHA-1 zgodnie z interoperacyjnością RFC 6238, 6 cyfr i wyłącznie bieżący krok 30 sekund. Poprzednie i przyszłe kroki nie są akceptowane; zapewnia to maksymalny czas ważności 30 sekund wymagany w ASVS 5.0.0 V6.5.5. Serwer wymaga zsynchronizowanego zegara. Zaakceptowany krok nie może zostać użyty ponownie.
- Challenge i kody odzyskiwania: losowe wartości; w SQLite zapisują się wyłącznie SHA-256 hashe. Nowe kody odzyskiwania mają 128 bitów entropii, więc nie wymagają wolnego hashowania przeznaczonego dla słabych, zgadywalnych sekretów. Wcześniej wydane kody 16-znakowe mają 96 bitów; pozostają ważne dla kompatybilności i nie można ich bezpiecznie przekształcić bez znajomości wartości jawnej. Są ograniczeniem migracyjnym do rozwiązania przez bezpieczną rotację kodów.
- Sesje są tworzone dopiero po poprawnym drugim kroku MFA. Aktywacja/wyłączenie unieważnia wszystkie sesje.
- Zmiana hasła usuwa challenge logowania i niepotwierdzony sekret konfiguracji.
- Tabele: `user_totp`, `totp_login_challenges`, `totp_recovery_codes`.

## Weryfikacja w repozytorium

Z katalogu `backend/` uruchom:

```sh
.venv/bin/python -m pytest -q
```

Testy MFA obejmują wektory RFC 6238, zgodność parametrów provisioning URI, akceptację bieżącego oraz odrzucanie poprzedniego i przyszłego kroku, setup i wygaśnięcie setupu oraz challenge, brak sekretu jawnego w bazie, brak tokenu po pierwszym kroku logowania, jednorazowość challenge/TOTP/kodów odzyskiwania, blokadę prób, unieważnianie sesji, brak klucza, modyfikację ciphertext oraz równoległe wykorzystanie challenge.

## Podstawa zaleceń

- [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
- [RFC 6238 — TOTP](https://www.rfc-editor.org/rfc/rfc6238)
- [RFC 4226 — HOTP](https://www.rfc-editor.org/rfc/rfc4226)
