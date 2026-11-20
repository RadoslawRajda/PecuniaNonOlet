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
| Operacje finansowe | Transakcje DB, idempotencja, kontrola właściciela rachunku, blokada współbieżności i audyt w tej samej transakcji | Pełne testy regresji w tej iteracji nie mogły zostać uruchomione |

## Weryfikacja wykonana w tej iteracji

- `ruff check app tests`: **zaliczone**.
- `python3 -m compileall -q app migrations tests`: **zaliczone**.
- `python3 -m pytest -q tests`: **nie uruchomiło testów** — interpreter nie ma modułu `pydantic_settings`. Nie jest to wynik fail/pass suite; przed akceptacją należy uruchomić testy w środowisku z `requirements.lock.txt`.
- Nowe testy obejmują listę aktywnych sesji, cofanie innej sesji, wymaganie świeżego uwierzytelnienia, body limits, nagłówki HTTP, hasła popularne/kontekstowe, uprawnienia pliku bazy i logi bez sekretów. Są dodane, ale wymagają rzeczywistego uruchomienia pytest.
- Nie wykonano testu launchera, pełnego builda mobilnego ani testów end-to-end na iOS/Android.

## Otwarte punkty przed deklaracją zgodności ASVS L2

1. Uruchomić pełny zestaw testów na przypiętych zależnościach i w CI; obecny brak `pydantic_settings` blokuje lokalną weryfikację.
2. Uzupełnić ocenę każdej pozycji w [macierzy L2](ASVS_5.0.0_L2_MATRIX.md). Pozycje „Nieocenione” są otwarte, nie zaliczone.
3. Dodać centralne, rozdzielone od bazy aplikacji logowanie, retencję, alertowanie i monitoring błędów TLS.
4. Ustalić szyfrowanie danych SQLite w spoczynku i zarządzanie/rotację `MFA_ENCRYPTION_KEY` dla docelowego wdrożenia.
5. Uzupełnić breached-password screening wiarygodnym źródłem lokalnym lub usługą prywatnościową. Aktualne 3000 haseł to częściowe zabezpieczenie.
6. Zweryfikować HTTPS, konfigurację zaufanych hostów, rate limiting i zachowanie sesji przy rzeczywistym uruchomieniu aplikacji.
7. Dodać testy end-to-end odświeżania tokenów i cofania sesji na kliencie mobilnym oraz scenariusz odtwarzania po utracie urządzenia/MFA.

## Wniosek

Krótkie access tokeny i rotowane refresh tokeny są zaimplementowane z atomowym odświeżaniem, wykrywaniem replay i unieważnianiem rodziny sesji. Dodano również API do przeglądu i cofania sesji. Nie deklaruję jeszcze pełnej zgodności OWASP ASVS L2: uruchomienie testów backendu jest zablokowane zależnością środowiska, a macierz zawiera wymagania nieocenione.
