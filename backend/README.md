# Backend PecuniaNonOlet

Backend FastAPI z rejestracją, logowaniem i wylogowaniem. Konta oraz sesje są przechowywane w SQLite, a schemat bazy jest zarządzany przez Alembic. Skrypt uruchamia API i ogłasza je w sieci lokalnej przez mDNS.

## Wymagania

- Python 3.10 lub nowszy
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

## Endpointy

| Metoda | Ścieżka | Działanie |
| --- | --- | --- |
| `POST` | `/api/register` | Rejestracja, utworzenie rachunków walutowych i wydanie tokenu |
| `POST` | `/api/login` | Logowanie i wydanie tokenu |
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

Rejestracja i logowanie przyjmują JSON: `{"email":"test@example.com","password":"haslo1234"}`. Hasło przy rejestracji musi mieć od 8 do 128 znaków. Odpowiedź zawiera `user`, `token`, `token_type` i `expires_in`. Dla `/api/me` i `/api/logout` wyślij nagłówek `Authorization: Bearer <token>`. Token wygasa po 7 dniach, a wylogowanie unieważnia go od razu.

Gdy użytkownik ma włączone MFA, `/api/login` zamiast tokenu zwraca `mfa_required: true`, `challenge_token` i `expires_in`. Frontend kończy logowanie przez `POST /api/login/mfa`. Szczegółowy przepływ konfiguracji, przykładowe żądania i odpowiedzi opisuje [dokumentacja MFA TOTP](docs/TOTP_MFA.md). Przed włączeniem MFA ustaw na komputerze backendu zmienną `MFA_ENCRYPTION_KEY`; wygeneruj ją poleceniem `.venv/bin/python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` (Windows: `.venv\\Scripts\\python.exe -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`). Zachowaj ją poza repozytorium i używaj tej samej wartości po każdym restarcie. To klucz szyfrujący sekrety TOTP w bazie i nie jest tym samym co lokalny CA TLS.

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

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Na Windows użyj `.venv\Scripts\python.exe` zamiast `.venv/bin/python`.

Hasła są zapisywane jako hashe Argon2, a w bazie przechowywane są tylko hashe tokenów i kodów MFA. Odpowiedzi API mają `Cache-Control: no-store`. Próby kodów MFA są limitowane per konto. Połączenie lokalne korzysta z HTTPS z prywatnym CA, który użytkownik musi jawnie zainstalować i zweryfikować na telefonie. Backend nadal jest demonstracyjny, nie do publicznego wdrożenia; użycie z prawdziwymi kontami wymaga publicznie zaufanego TLS, limitowania prób logowania hasłem i monitorowania zdarzeń logowania.
