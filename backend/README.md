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
| `POST` | `/api/register` | Rejestracja i wydanie tokenu |
| `POST` | `/api/login` | Logowanie i wydanie tokenu |
| `GET` | `/api/me` | Dane zalogowanego użytkownika |
| `POST` | `/api/logout` | Unieważnienie tokenu |
| `POST` | `/api/change-password` | Zmiana hasła i unieważnienie wszystkich sesji użytkownika |

Rejestracja i logowanie przyjmują JSON: `{"email":"test@example.com","password":"haslo1234"}`. Hasło przy rejestracji musi mieć od 8 do 128 znaków. Odpowiedź zawiera `user`, `token`, `token_type` i `expires_in`. Dla `/api/me` i `/api/logout` wyślij nagłówek `Authorization: Bearer <token>`. Token wygasa po 7 dniach, a wylogowanie unieważnia go od razu.

Nowe konta otrzymują rolę `user`, której nie można wybrać w żądaniu rejestracji. Konto `analyst` może utworzyć zaufany lokalny administrator po migracji bazy:

```sh
.venv/bin/python -m app.admin create-analyst analityk@example.com
```

Hasło jest wpisywane interaktywnie i nie trafia do argumentów procesu. Pole `user.role` jest zwracane przez logowanie, rejestrację i `/api/me`.

Zmiana hasła wymaga nagłówka `Authorization: Bearer <token>` oraz JSON `{"current_password":"stare","new_password":"nowe-haslo"}`. Sukces zwraca `reauthentication_required: true`; użytkownik musi zalogować się ponownie.

## Testy

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Na Windows użyj `.venv\Scripts\python.exe` zamiast `.venv/bin/python`.

Hasła są zapisywane jako hashe Argon2, a w bazie przechowywane są tylko hashe tokenów. Połączenie w sieci lokalnej korzysta z HTTP, więc do testów używaj fikcyjnych danych. Przed użyciem z prawdziwymi kontami potrzebne jest HTTPS.
