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

Skrypt tworzy środowisko `.venv`, instaluje biblioteki, wybiera adres IP i uruchamia FastAPI na porcie 8000. Przy starcie backend automatycznie wykonuje oczekujące migracje Alembic. Jeśli komputer ma kilka adresów, poprosi o wybór. Adres można podać ręcznie:

```sh
./start-unix.sh --ip 192.168.1.45
```

Na Windows: `start-windows.bat --ip 192.168.1.45`.

Po starcie otwórz adres podany w terminalu, np. `http://192.168.1.45:8000/`. Strona `/` pokazuje proste informacje diagnostyczne. Dokumentacja API jest pod `/docs`, a kontrola stanu pod `/health`. Usługa mDNS ma typ `_pecunianonolet._tcp.local.`; nazwa `pecunianonolet.local` działa tylko na urządzeniach obsługujących mDNS.

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
| `POST` | `/api/logout` | Unieważnienie tokenu |
| `POST` | `/api/change-password` | Zmiana hasła i unieważnienie wszystkich sesji użytkownika |

Rejestracja i logowanie przyjmują JSON: `{"email":"test@example.com","password":"haslo1234"}`. Hasło przy rejestracji musi mieć od 8 do 128 znaków. Odpowiedź zawiera `user`, `token`, `token_type` i `expires_in`. Dla `/api/me` i `/api/logout` wyślij nagłówek `Authorization: Bearer <token>`. Token wygasa po 7 dniach, a wylogowanie unieważnia go od razu.

Nowe konta otrzymują rolę `user`, której nie można wybrać w żądaniu rejestracji. Konto `analyst` może utworzyć zaufany lokalny administrator po migracji bazy:

```sh
.venv/bin/python -m app.admin create-analyst analityk@example.com
```

Hasło jest wpisywane interaktywnie i nie trafia do argumentów procesu. Pole `user.role` jest zwracane przez logowanie, rejestrację i `/api/me`.

Endpointy analityczne wymagają tokenu konta `analyst`. Lista użytkowników przyjmuje `limit` (1–100), `offset` oraz opcjonalne `role`. Lista transakcji przyjmuje `limit`, `offset`, `kind`, `status`, `user_id` oraz zakres czasu `from` i `to` jako znaczniki czasu Unix. Odpowiedzi zawierają wyłącznie dane potrzebne do analizy; nie zwracają hashy haseł ani tokenów sesji. Podsumowanie pokazuje liczniki bez ujawniania danych uwierzytelniających.

Zmiana hasła wymaga nagłówka `Authorization: Bearer <token>` oraz JSON `{"current_password":"stare","new_password":"nowe-haslo"}`. Sukces zwraca `reauthentication_required: true`; użytkownik musi zalogować się ponownie.

Rejestracja tworzy osobne rachunki PLN, EUR, USD, GBP i CZK. Rachunek PLN otrzymuje jednorazowe saldo początkowe 1000,00 PLN, zapisane jako transakcja otwarcia i wpis księgowy; pozostałe rachunki rozpoczynają z saldem 0,00. Migracja Alembic uzupełnia rachunki istniejących użytkowników bez resetowania sald.

Lista historii przyjmuje `limit` (1–100, domyślnie 20) i `offset` (domyślnie 0), sortuje wpisy deterministycznie od najnowszych. Kwoty są zwracane jako całkowita liczba najmniejszych jednostek oraz tekst dziesiętny; wymiany zawierają obie kwoty i utrwalony kurs. Dostęp do historii jest ograniczony do nadawcy lub odbiorcy danej operacji.

Przelew wymaga nagłówków `Authorization: Bearer <token>` i `Idempotency-Key` oraz JSON zawierającego `recipient_email`, `source_account_id`, `currency_code` i dodatnie `amount_minor`. Kwota jest pobierana i księgowana w tej samej walucie; brak środków na wybranym rachunku nie powoduje użycia innego rachunku. Ponowienie tego samego żądania z tym samym kluczem zwraca poprzedni przelew bez ponownego księgowania; użycie klucza dla innej operacji kończy się konfliktem.

Kursy są pobierane z API NBP przez HTTPS. Endpoint wyceny przyjmuje `source_account_id`, `destination_account_id` i `source_amount_minor`; zwraca kwotę docelową, kurs, datę tabeli NBP oraz identyfikator i termin ważności wyceny. NBP podaje kursy względem PLN, a kursy między pozostałymi walutami są wyliczane jako kursy krzyżowe. Realizacja przyjmuje `quote_id` i nagłówek `Idempotency-Key`; kursu podanego przez klienta backend nie przyjmuje. Kwoty są zaokrąglane do najmniejszej jednostki waluty regułą `ROUND_HALF_UP`. Brak dostępnych lub niekompletnych kursów zwraca błąd usługi, bez kursu zastępczego.

Zdjęcie przesyłaj jako `multipart/form-data` w polu `file` na `PUT /api/profile/photo`. Backend dopuszcza JPEG, PNG i WebP do 2 MiB, sprawdza format na podstawie zawartości, odrzuca animacje i obrazy o nadmiernych wymiarach, a zapisuje przetworzony JPEG bez metadanych EXIF. Pliki przechowywane są poza katalogiem publicznym, pod losową nazwą; pobranie i usunięcie wymagają aktywnej sesji właściciela. Katalog można zmienić zmienną `PROFILE_PHOTO_DIR`; domyślnie znajduje się obok pliku bazy danych.

## Testy

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Na Windows użyj `.venv\Scripts\python.exe` zamiast `.venv/bin/python`.

Hasła są zapisywane jako hashe Argon2, a w bazie przechowywane są tylko hashe tokenów. Połączenie w sieci lokalnej korzysta z HTTP, więc do testów używaj fikcyjnych danych. Przed użyciem z prawdziwymi kontami potrzebne jest HTTPS.
