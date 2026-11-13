# Raport kryptografia

## 1. Kryptografia w aplikacji

### 1.1. Tabela

| Miejsce w aplikacji | Zadanie | Co jest teraz (plik:linia) | Klucz: skąd i gdzie | Problem | Decyzja i źródło |
|---|---|---|---|---|---|
| Token sesji | Poufność | `useAppController.ts:18-22, 58-66` - `react-native-keychain` | Systemowy Keychain/Keystore | Brak | Pozostawić Keychain/Keystore |
| Logowanie i rejestracja | Poufność danych | `useAppController.ts:130-154` - żądania `fetch` do API | Brak klucza TLS przy HTTP | Hasło i token mogą zostać przechwycone | HTTPS |
| Odtwarzanie sesji | Uwierzytelnianie | `useAppController.ts:69-101` - sprawdzenie tokenu przez `/api/me` | Token z Keychain | Po błędzie sieci aplikacja otwiera dashboard z prośbą o ponowne potwierdzenie sesji | Można pozostawić |
| Rola analityka | Kontrola dostępu | `useAppController.ts:18-23, 32-49` - rola w AsyncStorage, ograniczenie ekranów | Brak klucza; rola nie jest sekretem | Lokalna rola może być zmieniona | Weryfikować uprawnienia przez API, nie ufać lokalnej roli |

### 1.2. Kategorie błędów

| Kategoria | Wynik | Jak szukaliśmy |
|---|---|---|
| Klucz w kodzie | Brak | `useAppController.ts`, konfiguracja Keychain |
| Przestarzały algorytm lub tryb | Brak | Przegląd mechanizmów przechowywania tokenu |
| Przewidywalna losowość | Nie stwierdzono; generowanie tokenu odbywa się na backendzie | Przegląd kontrolera uwierzytelniania |
| Powtarzane wartości jednorazowe | Generowanie klucza TOTP będzie odbywać się na backendzie | Backend |
| Hasło jako zwykły skrót | Nie dotyczy aplikacji mobilnej | Hasła są przesyłane do backendu |
| Szyfrowanie bez integralności | Komunikacja HTTP nie jest chroniona | Przegląd `fetch` i dokumentacji API |

## 2. Stan aplikacji i plan

### 2.1. Stan aplikacji

| Obszar | Status | Największe ryzyko |
|---|---|---|
| Funkcje (MVP) | Najważniejsze funkcje zostały zaimplementowane | Brak |
| Build z repozytorium | Niepotwierdzony | Nie wykonano czystego buildu; główny README jest niepełny |
| Model zagrożeń | Istnieje | Brak |
| Uprawnienia | Zaimplementowane | Przechowywanie lokalne, lecz jest weryfikowane przez frontend i backend |
| Przechowywanie danych | Zaimplementowane | Brak |
| Kryptografia | Warunkowo | Komunikacja HTTP bez TLS |

### 2.3. Plan do zajęć 6

| Zadanie | Kto | Termin | Sposób sprawdzenia |
|---|---|---|---|
| Wprowadzić HTTPS | Osoba od backendu | Zajęcia 6 | Sprawdzenie połączenia TLS |
| Uzupełnić README i sprawdzić build | Osoba od dokumentacji | Zajęcia 6 | Czysty klon i build według README |
| Dodać kody QR generowane przez backend | Osoba od backendu | Zajęcia 6 | Testy |
