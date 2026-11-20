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

## Konkretne kontrole i testy ASVS

Kontrole dotyczące sesji i uwierzytelniania zostały sprawdzone w kodzie oraz testach, w tym rotacja refresh tokenu, wykrywanie jego ponownego użycia, unieważnianie rodziny, ograniczenia liczby sesji, świeżość reautoryzacji, weryfikacja OIDC, WebAuthn UV i wyzwania jednorazowe. Testy integracyjne znajdują się przede wszystkim w `tests/test_app.py`, `tests/test_google_passkeys.py`, `tests/test_mfa.py` i `tests/test_rate_limits.py`. Kontrole finansowe oraz spójność transakcji są pokryte w `tests/test_exchange.py`, `tests/test_audit.py` i `tests/test_analytics.py`.

Zidentyfikowane podczas tej pracy problemy i poprawki regresyjne:

- wyczerpanie limitu jednego klucza limiterów nie zwiększa już innych kluczy, co ogranicza niezamierzone blokowanie wspólnego adresu IP; sprawdza to `test_blocked_request_does_not_consume_other_rate_limit_buckets`;
- challenge logowania Google i passkey ma maksymalnie pięć kosztownych prób weryfikacji; następne próby są odrzucane przed weryfikacją podpisu; sprawdza to `test_google_login_stops_verifying_after_challenge_attempt_limit`;
- błędne `crossOrigin`/`topOrigin` jest odrzucane dla rejestracji i uwierzytelniania WebAuthn;
- świeżość uwierzytelnienia Google jest sprawdzana w `assert_recent_authentication`; brak lub nieaktualny `auth_time` nie może autoryzować zmiany metod uwierzytelniania.

To nie stanowi pełnej oceny wszystkich 183 wymagań L2. Szczegółowa macierz rozróżnia wymagania otwarte od N/D; w tej iteracji nie deklaruje się certyfikacji ani pełnej zgodności.

## Weryfikacja wykonana w tej iteracji

- Python 3.11, przypięte `requirements.lock.txt`: **188 testów zaliczonych**; Ruff lint, Ruff format oraz mypy zaliczone.
- Python 3.12 i 3.13, przypięte `requirements.lock.txt`: bazowy stan sprzed ostatnich zmian przeszedł **184 testy** na każdej wersji; po poprawkach limitów prób i limiterów należy powtórzyć pełny przebieg.
- `pip-audit -r requirements.lock.txt`: **brak znanych podatności** przy ostatnim uruchomieniu. To wynik bazy advisory w chwili audytu, nie gwarancja bezpieczeństwa zależności.
- Testy obejmują aktywne sesje, cofanie sesji, świeże uwierzytelnienie, limity body, nagłówki, politykę haseł, prywatność pliku bazy, brak sekretów w logach, limity prób, rate limiting, migracje, transakcje i regresje finansowe.
- Nie wykonano testu launchera, pełnego builda mobilnego ani testów end-to-end na iOS/Android.

## Otwarte punkty przed deklaracją zgodności ASVS L2

1. Powtórzyć pełny zestaw na Pythonie 3.11–3.13 po ostatnich zmianach i potwierdzić wykonanie w CI.
2. Uzupełnić ocenę każdej pozycji w [macierzy L2](ASVS_5.0.0_L2_MATRIX.md). Pozycje „Nieocenione” są otwarte, nie zaliczone.
3. Dodać centralne, rozdzielone od bazy aplikacji logowanie, retencję, alertowanie i monitoring błędów TLS.
4. Ustalić szyfrowanie danych SQLite w spoczynku i zarządzanie/rotację `MFA_ENCRYPTION_KEY` dla docelowego wdrożenia.
5. Uzupełnić breached-password screening wiarygodnym źródłem lokalnym lub usługą prywatnościową. Aktualne 3000 haseł to częściowe zabezpieczenie.
6. Zweryfikować HTTPS, konfigurację zaufanych hostów, rate limiting i zachowanie sesji przy rzeczywistym uruchomieniu aplikacji.
7. Dodać testy end-to-end odświeżania tokenów i cofania sesji na kliencie mobilnym oraz scenariusz odtwarzania po utracie urządzenia/MFA.

## Wniosek

Krótkie access tokeny i rotowane refresh tokeny są zaimplementowane z atomowym odświeżaniem, wykrywaniem replay i unieważnianiem rodziny sesji. Dodano również API do przeglądu i cofania sesji. Nie deklaruję pełnej zgodności OWASP ASVS L2: macierz nadal zawiera wymagania nieocenione, a konfiguracja produkcyjna i aplikacje mobilne wymagają osobnych testów.
