# Przegląd bezpieczeństwa backendu

## Zakres

Przegląd dotyczy backendu na branchu `feature/backend-hardening` oraz bieżących, lokalnych zmian. Głównym punktem odniesienia jest OWASP ASVS 5.0.0 L2. Pełny wykaz wymagań i ich status jest w [macierzy ASVS](ASVS_5.0.0_L2_MATRIX.md). To przegląd techniczny, nie certyfikacja ani deklaracja zgodności.

## Zmiany w sesjach

- Access token jest nieprzezroczysty, losowy i ważny maksymalnie 15 minut. W bazie przechowywany jest jego SHA-256, a nie wartość jawna.
- Refresh token jest nieprzezroczysty, losowy i ważny do 30 dni bezczynności, maksymalnie 90 dni od utworzenia sesji. Każde odświeżenie atomowo rotuje oba tokeny.
- Skróty zużytych refresh tokenów są przechowywane, aby wykryć replay; ponowne użycie unieważnia rodzinę sesji.
- Logout unieważnia rodzinę wskazaną przez refresh token, także gdy access token wygasł. Zmiana hasła i ustawień MFA unieważnia aktywne sesje.
- Limit wynosi 5 aktywnych sesji na konto. Dodane API `GET /api/sessions`, `DELETE /api/sessions/{session_id}` i `POST /api/sessions/revoke-others` pozwalają obejrzeć sesje oraz cofnąć pozostałe po świeżym uwierzytelnieniu.
- Migracja 0013 wymaga ponownego logowania po aktualizacji. Migracja 0014 tworzy append-only rejestr zdarzeń bezpieczeństwa.

## Kontrole i dowody

| Obszar | Implementacja | Ograniczenia |
|---|---|---|
| TOTP | RFC 6238; sekrety szyfrowane AES-GCM; weryfikacja z ochroną przed replay i limitami prób; jednorazowe kody odzyskiwania | Klucz szyfrujący pozostaje w konfiguracji operatora; nie ma KMS/HSM ani procedury bezprzerwowej rotacji klucza |
| Passkeys | Weryfikacja WebAuthn przez bibliotekę; challenge związany z ceremonią i sesją; kontrola pochodzenia i RP ID | Nie przeprowadzono testu na fizycznym urządzeniu ani pełnego audytu zgodności wszystkich platform |
| Logowanie Google | OIDC z walidacją podpisu, issuer, audience, czasu i nonce; stałe źródło kluczy | Nie sprawdzono rzeczywistej integracji z Google w tej iteracji |
| Hasła | Argon2id, walidacja długości, lokalna lista 3000 popularnych haseł i słów kontekstowych bez wysyłania hasła poza backend | Lista nie jest pełną bazą wyciekłych haseł; kontrola ASVS dla breached-password screening jest częściowa |
| HTTP | API ustawia `no-store`; nagłówki ochronne i HSTS przy HTTPS; limit body 16 KiB dla auth i 1 MiB dla pozostałych żądań (z osobnymi limitami uploadów) | HSTS, TLS i hosty muszą być zweryfikowane w konkretnym launcherze i na urządzeniu; CSP Swaggera developerskiego ma wyjątki wymagane przez UI |
| Throttling | Trwałe limity SQLite dla loginu, MFA, passkeys, CAPTCHA oraz transferów i wymian; odpowiedź 429 | SQLite i limity per instancja są przeznaczone do lokalnego MVP, nie do skalowania wielu węzłów |
| Baza | Plik bazy tworzony jako prywatny na POSIX; odrzucane dowiązanie symboliczne; parametryzowane SQL i transakcje finansowe | SQLite nie szyfruje pliku w spoczynku; uprawnienia systemu plików zależą od platformy |
| Rejestr zdarzeń | Loguje wynik auth, sesji, zmian poświadczeń i odmów 401/403; nie zapisuje haseł, tokenów, body ani e-maili; wpisy niezmienne przez SQL trigger | Lokalna baza nie jest odseparowanym centralnym systemem. Brak retencji/alertowania i centralnego monitoringu; ASVS 16.4.3 pozostaje otwarty |
| Request validation | Odpowiedzi 422 nie odbijają wejściowych wartości, aby nie ujawnić haseł i tokenów | Wymaga dalszego przeglądu pozostałych ścieżek logowania i wyjątków |
| Operacje finansowe | Transakcje DB, idempotencja, kontrola właściciela rachunku, blokada współbieżności i audyt w tej samej transakcji | SQLite jest przeznaczone dla lokalnego MVP; zakres testów opisano niżej |

### Klasyfikacja danych i log inventory (zakres backendu)

| Dane | Klasyfikacja robocza | Kontrola i ograniczenie |
|---|---|---|
| Hasło, TOTP seed, kody recovery | Sekret uwierzytelniający — najwyższa poufność | Hasło Argon2id; TOTP szyfrowany AES-GCM; recovery przechowywane jako hash. Brak KMS/HSM i rotacji bez przestoju. |
| Access/refresh tokeny, challenge | Sekret sesyjny | Tokeny losowe; w bazie hashe; refresh rotowany i replay unieważnia rodzinę. Odpowiedzi API `no-store`. |
| Salda, przelewy, wymiany, historia | Wrażliwe dane finansowe | Autoryzacja właściciela/roli, parametryzowane zapytania, transakcje; SQLite bez szyfrowania at-rest. |
| E-mail i identyfikatory kont | Dane osobowe | Ograniczenie dostępu w API; nie są zapisywane w security-event logach. Polityka usunięcia/retencji wymaga decyzji wdrożeniowej. |
| Zdjęcie profilowe | Dane osobowe | Walidacja i re-encoding, limit rozmiaru/pikseli; katalog lokalny nie jest zaszyfrowany. |
| Klucz MFA, klucze TLS i provider secrets | Sekrety operatora | Wczytywane z konfiguracji środowiska; brak zewnętrznego secret managera i audytu systemu hosta. |
| Klucz publiczny passkey i rekord audytowy | Dane integralności/bezpieczeństwa | Klucz publiczny nie jest sekretem; audyt finansowy i security events są lokalne w SQLite, z ochroną integralności na poziomie aplikacji/triggerów. |

Logowanie backendu składa się z: (1) Python/Uvicorn loggerów operacyjnych na stderr, (2) strukturalnych zdarzeń bezpieczeństwa w tabeli SQLite przez `app/security_events.py`, oraz (3) zdarzeń audytu finansowego w SQLite przez `app/audit.py`. Zdarzenia bezpieczeństwa obejmują wynik logowania, metodę, endpoint i czas; nie powinny zawierać haseł, tokenów, body ani e-maili. Logi lokalne nie są odseparowane od hosta aplikacji, nie mają skonfigurowanej retencji, centralizacji ani alertowania. Te luki są ocenione jako częściowe/brakujące w macierzy V14/V16.

### Polityka WebAuthn i OIDC

- Passkeys są weryfikowane przez bibliotekę `webauthn`; wymagane jest User Verification, właściwy typ ceremonii, challenge, RP ID i origin. Discoverable login wymaga `userHandle` powiązanego z kontem oraz zgodności `id` z `rawId`.
- `crossOrigin` musi mieć wartość `false` lub być pominięte, a `topOrigin` nie może występować. Reguła dotyczy rejestracji i asercji; testy odrzucają każdą z trzech niedozwolonych kombinacji.
- `signCount=0` jest akceptowany, także przy powtórnych asercjach. Backend nie interpretuje flag backup eligibility/state (BE/BS), nie przechowuje ich i nie używa ich do autoryzacji ani oceny ryzyka. To świadoma polityka dla passkeys synchronizowanych; nie zapewnia detekcji klonowania opartej o licznik urządzenia.
- Google identity jest kluczowana po providerze, kanonicznym issuerze i subject. Reautoryzacja do zmian wrażliwych wymaga świeżego `auth_time`; sama nowa sesja, nonce ani `prompt=select_account` nie są uznawane za dowód świeżego logowania. Jeśli Google nie zwróci `auth_time`, operacja jest odrzucana.
- Dla logowania mobilnego klient używa Authorization Code + PKCE w systemowym flow AppAuth. ID token Google jest tylko wejściem do backendowego OIDC verifiera; API wydaje własne opaque sesje.
- Klient dodaje `max_age=0` oraz żądanie claimu `auth_time` do autoryzacji Google. Zgodnie z OIDC Core `max_age=0` żąda aktywnej reautoryzacji; samo `prompt=select_account` zapewnia tylko wybór konta. Backend nadal ufa wyłącznie zweryfikowanemu `auth_time` i odrzuca brak, niepoprawną lub zbyt starą wartość przy zmianie metod logowania.

Ręczna weryfikacja na urządzeniu: na iOS i Androidzie wykonaj logowanie Google przez systemowy AppAuth, zakończ MFA jeśli jest włączone, a następnie spróbuj dodać passkey, skonfigurować TOTP, ustanowić hasło oraz cofnąć inne sesje. Sprawdź, że `provider_authenticated_at` sesji odpowiada ostatniemu aktywnemu logowaniu u Google i że operacje wrażliwe przechodzą w ciągu 5 minut. Po upływie 5 minut powinny zwrócić 401; ponowny przepływ Google powinien dać nowy dowód. Dla linkowania Google zweryfikuj także, że `subject` tokenu należy do wybranego konta. Ta próba wymaga skonfigurowanych identyfikatorów Google i urządzenia; nie została wykonana w tej iteracji. Testy lokalne używają kontrolowanych, podpisanych tokenów i nie zastępują testu dostawcy.

## Konkretne kontrole i testy ASVS

Kontrole dotyczące sesji i uwierzytelniania zostały sprawdzone w kodzie oraz testach, w tym rotacja refresh tokenu, wykrywanie jego ponownego użycia, unieważnianie rodziny, ograniczenia liczby sesji, świeżość reautoryzacji, weryfikacja OIDC, WebAuthn UV i wyzwania jednorazowe. Testy integracyjne znajdują się przede wszystkim w `tests/test_app.py`, `tests/test_google_passkeys.py`, `tests/test_mfa.py` i `tests/test_rate_limits.py`. Kontrole finansowe oraz spójność transakcji są pokryte w `tests/test_exchange.py`, `tests/test_audit.py` i `tests/test_analytics.py`.

Zidentyfikowane podczas tej pracy problemy i poprawki regresyjne:

- wyczerpanie limitu jednego klucza limiterów nie zwiększa już innych kluczy, co ogranicza niezamierzone blokowanie wspólnego adresu IP; sprawdza to `test_blocked_request_does_not_consume_other_rate_limit_buckets`;
- challenge logowania Google i passkey ma maksymalnie pięć kosztownych prób weryfikacji; następne próby są odrzucane przed weryfikacją podpisu; sprawdza to `test_google_login_stops_verifying_after_challenge_attempt_limit`;
- błędne `crossOrigin`/`topOrigin` jest odrzucane dla rejestracji i uwierzytelniania WebAuthn;
- świeżość uwierzytelnienia Google jest sprawdzana w `assert_recent_authentication`; brak lub nieaktualny `auth_time` nie może autoryzować zmiany metod uwierzytelniania.

Macierz zawiera indywidualny status i uzasadnienie dla wszystkich 183 wymagań L2, lecz nie jest formalną oceną certyfikacyjną. Wiele kontroli pozostaje częściowych lub niespełnionych; nie deklaruje się zgodności L2.

## Weryfikacja wykonana w tej iteracji

- Python 3.11, 3.12 i 3.13, przypięte `requirements.lock.txt`: **188 testów zaliczonych na każdej wersji**; Ruff lint, Ruff format oraz mypy zaliczone na każdej wersji.
- `pip-audit -r requirements.lock.txt`: **brak znanych podatności** przy ostatnim uruchomieniu. To wynik bazy advisory w chwili audytu, nie gwarancja bezpieczeństwa zależności.
- Testy obejmują aktywne sesje, cofanie sesji, świeże uwierzytelnienie, limity body, nagłówki, politykę haseł, prywatność pliku bazy, brak sekretów w logach, limity prób, rate limiting, migracje, transakcje i regresje finansowe.
- Nie wykonano testu launchera, pełnego builda mobilnego ani testów end-to-end na iOS/Android.

Źródła standardów: [OWASP ASVS 5.0.0](https://github.com/OWASP/ASVS/tree/v5.0.0), [WebAuthn Level 3](https://www.w3.org/TR/webauthn-3/), [OIDC Core](https://openid.net/specs/openid-connect-core-1_0.html), [OAuth Security BCP RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html), [PKCE RFC 7636](https://www.rfc-editor.org/rfc/rfc7636.html), [Native Apps RFC 8252](https://www.rfc-editor.org/rfc/rfc8252.html) i [JWT BCP RFC 8725](https://www.rfc-editor.org/rfc/rfc8725.html).

## Otwarte punkty przed deklaracją zgodności ASVS L2

1. Potwierdzić wykonanie bieżącego workflow CI na remote; lokalne wyniki nie stanowią potwierdzenia zewnętrznego CI.
2. Dodać centralne, rozdzielone od bazy aplikacji logowanie, retencję, alertowanie i monitoring błędów TLS.
3. Ustalić szyfrowanie danych SQLite w spoczynku i zarządzanie/rotację `MFA_ENCRYPTION_KEY` dla docelowego wdrożenia.
4. Uzupełnić breached-password screening wiarygodnym źródłem lokalnym lub usługą prywatnościową. Aktualne 3000 haseł to częściowe zabezpieczenie.
5. Zweryfikować HTTPS, konfigurację zaufanych hostów, rate limiting i zachowanie sesji przy rzeczywistym uruchomieniu aplikacji.
6. Dodać testy end-to-end odświeżania tokenów i cofania sesji na kliencie mobilnym oraz scenariusz odtwarzania po utracie urządzenia/MFA.
7. Zweryfikować osobno klienta mobilnego i host/proxy/firewall; ocena ASVS backendu nie zastępuje audytu tych warstw.

## Wniosek

Krótkie access tokeny i rotowane refresh tokeny są zaimplementowane z atomowym odświeżaniem, wykrywaniem replay i unieważnianiem rodziny sesji. Dodano również API do przeglądu i cofania sesji. Nie deklaruję pełnej zgodności OWASP ASVS L2: macierz nadal zawiera wymagania nieocenione, a konfiguracja produkcyjna i aplikacje mobilne wymagają osobnych testów.
