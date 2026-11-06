# Bezpieczne przechowywanie danych

---

# D1 – Inwentaryzacja danych na urządzeniu

| Dane | Gdzie są teraz | Klasyfikacja | Musi być na urządzeniu? | Docelowe miejsce i opcja |
|---|---|---|---|---|
| Token sesji | AsyncStorage, klucz `@app_auth_token` | Poufne | Tak – utrzymywanie zalogowanej sesji | `react-native-keychain`, Android Keystore / iOS Keychain, `ThisDeviceOnly` |
| Adres serwera API | Konfiguracja aplikacji `API_URL` | Wewnętrzne | Tak – komunikacja z backendem | Konfiguracja aplikacji |
| Preferencje użytkownika | AsyncStorage | Wewnętrzne | Tak – indywidualne ustawienia użytkownika | Jest w odpowiedniej lokalizacji |

---

# D2 – Raport "przed" - stan bezpieczeństwa


| Miejsce | Co znaleziono | Ryzyko |
|---|---|---|
| AsyncStorage | Token sesji zapisany pod kluczem `@app_auth_token` bez szyfrowania na poziomie aplikacji | Wysokie |
| Logi React Native | Wywołania `console.error` podczas błędów odczytu tokenu i wylogowania | Średnie – wymaga testu treści logów |
| Kod diagnostyczny | Zakomentowane fragmenty wyświetlające pełne odpowiedzi API | Średnie – ryzyko ponownego włączenia |
| Android Keystore | Brak wykorzystania do przechowywania tokenu | Wysokie |
| iOS Keychain | Brak wykorzystania do przechowywania tokenu | Wysokie |
| Zrzuty ekranu | Brak zasłaniania wrażliwych ekranów | Średnie |

---

# D3 – Decyzje o magazynie danych

## 3.1. Token sesji

**Po co na urządzeniu:** utrzymywanie zalogowanej sesji.

**Klasyfikacja:** Poufne.

**Obecny magazyn:** AsyncStorage.

**Docelowy magazyn:** `react-native-keychain`.

**Uzasadnienie:**

Token pozwala na uwierzytelnianie żądań do backendu.
Nie powinien być przechowywany w zwykłych preferencjach.


## 3.2. Preferencje użytkownika

**Po co na urządzeniu:** zapamiętanie wybranego kraju, waluty

**Klasyfikacja:** Wewnętrzne.

**Magazyn:** AsyncStorage.

**Dostępność:** podczas działania aplikacji.

**Uzasadnienie:**

Niewrażliwe ustawienia nie wymagają Keystore ani Keychain.
Można zachować je po wylogowaniu.

---

# D4 – Mapa kanałów wycieku

| Kanał | Dotyczy nas? | Co tam trafia teraz | Jak zamkniemy | Jak sprawdzimy |
|---|---|---|---|---|
| Logi | Tak | Komunikaty błędów odczytu tokenu i wylogowania; brak potwierdzonego logowania wartości tokenu | Maskowanie danych wrażliwych, brak logowania tokenów i haseł, kontrola logów release | `adb logcat`, konsola Xcode, test wersji release |
| Kopia zapasowa | Tak | Potencjalnie dane lokalne aplikacji; Android ma już `allowBackup=false` | Token w Keystore/Keychain, `ThisDeviceOnly` na iOS, weryfikacja reguł backupu | Backup i przywrócenie danych na obu platformach |
| Zrzuty ekranu / przełącznik | Tak | Dashboard z e-mailem, przyszłe dane finansowe i transakcje | Android: `FLAG_SECURE` na wrażliwych ekranach; iOS: zasłona po przejściu w tło | Zrzut ekranu i przełącznik aplikacji |
| Schowek | Nie – obecnie; możliwe w przyszłości | Brak funkcji kopiowania sekretów; planowane dane przelewów | Nie kopiować tokenów i haseł; ograniczyć czas dostępności kopiowanych danych, jeśli funkcja powstanie | Przegląd kodu i test kopiowania |
| Klawiatura | Tak | E-mail i hasła z formularzy logowania/rejestracji | `secureTextEntry` dla haseł, wyłączona autokorekta, odpowiednie typy pól | Test klawiatury systemowej i zewnętrznej |
| Cache HTTP i WebView | Tak – HTTP obecnie, WebView planowany | Odpowiedzi API; docelowo kursy walut w WebView | `Cache-Control: no-store` dla danych wrażliwych, czyszczenie cache sesji, ograniczenie WebView do zaufanych źródeł | Inspekcja cache, nagłówków API i danych WebView |
| Pliki tymczasowe | Planowane przy zdjęciach | Zdjęcia profilowe | Usuwanie plików po wykorzystaniu, bez zapisywania sekretów | Inspekcja katalogów aplikacji |
| Powiadomienia | Tak | Podstawowe informacje o przelewie | Bez tokenów i pełnych danych transakcji w treści powiadomień | Przegląd kodu i test po implementacji |

---

# D5 – Polityka sesji


| Zdarzenie | Co usuwamy | Gdzie (magazyn) | Co zostaje | Jak sprawdzimy |
|---|---|---|---|---|
| Wylogowanie | Token, dane użytkownika | Keychain / Keystore, cache | Niewrażliwe preferencje użytkownika | Wylogowanie, restart i próba wejścia do dashboardu |
| Reinstalacja | Lokalny token i poprzednią sesję | Android: dane aplikacji; iOS: Keychain czyszczony podczas inicjalizacji nowej instalacji | Domyślna konfiguracja | Usunięcie aplikacji, reinstalacja, sprawdzenie braku sesji |
| Wygaśnięcie sesji | Nieważny token, dane sesji i cache chronionych odpowiedzi | Keychain / Keystore, cache | Niewrażliwe ustawienia UI | Wymuszenie HTTP 401 i sprawdzenie powrotu do logowania |
| Kopia zapasowa / nowe urządzenie | Brak przywracania aktywnej sesji | Keystore, Keychain `ThisDeviceOnly`, polityka backupu | Dozwolone niewrażliwe preferencje | Odtworzenie kopii na nowym urządzeniu |
| Zmiana hasła na serwerze | Tokeny unieważnione na backendzie, lokalny token po wykryciu unieważnienia | Backend, Keychain / Keystore | Niewrażliwe ustawienia | Zmiana hasła i próba użycia starego tokenu |

