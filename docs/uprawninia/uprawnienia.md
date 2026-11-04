
# Pecunia non olet (PCO) - Uprawnienia i model bezpieczeństwa

## 1. Kontekst projektu

**Nazwa aplikacji:** Pecunia non olet (PCO)  
**Technologia:** React Native  
**Backend:** Python + FastAPI  
**Repozytorium:** https://github.com/RadoslawRajda/PecuniaNonOlet

### Funkcjonalności wymagające uprawnień

W aplikacji planujemy wykorzystać trzy zasoby urządzenia:

1. **Lokalizacja** - określanie kraju użytkownika w celu automatycznego wyboru domyślnej waluty oraz prezentowania odpowiednich kursów walut.
2. **Galeria zdjęć** - umożliwienie użytkownikowi wybrania i ustawienia zdjęcia profilowego.
3. **Kamera** - skanowanie kodów QR zawierających dane przelewu lub odnośniki do funkcji aplikacji.

## 2. Tabela uprawnień

| Zasób | Cel | Kiedy prosimy o dostęp | Co przy odmowie |
|---|---|---|---|
| Lokalizacja | Określenie kraju użytkownika, wybór domyślnej waluty i dopasowanie prezentowanych kursów | Przy pierwszym użyciu funkcji automatycznego wykrywania waluty | Ręczny wybór kraju i waluty |
| Galeria zdjęć | Wybór zdjęcia profilowego | Po kliknięciu "Zmień zdjęcie profilowe" | Pozostawienie domyślnego awatara |
| Kamera | Skanowanie kodów QR do przelewów lub deep linków | Po uruchomieniu skanera QR | Ręczne wpisanie danych przelewu lub kodu |

## 3. Szczegółowa obsługa uprawnień

### 3.1. Lokalizacja

**Cel:** Automatyczne określenie kraju użytkownika i dopasowanie domyślnej waluty, np. Polska=PLN, Czechy=CZK, Niemcy=EUR.

**Zakres dostępu:**
- Lokalizacja tylko podczas korzystania z aplikacji.
- Preferowana lokalizacja przybliżona.
- Brak potrzeby dostępu do lokalizacji w tle.
- Brak ciągłego śledzenia użytkownika.

**Android:**
- ACCESS_COARSE_LOCATION
- ACCESS_FINE_LOCATION - nie jest planowane, ponieważ dokładna lokalizacja nie jest konieczna.

**iOS:**
- NSLocationWhenInUseUsageDescription

**Moment prośby:** Po wybraniu funkcji automatycznego wykrywania waluty, a nie podczas uruchamiania aplikacji.

**Obsługa odmowy:** Użytkownik może samodzielnie wybrać kraj i domyślną walutę. Pozostałe funkcje aplikacji działają normalnie.

**Minimalizacja danych:** Wykorzystujemy lokalizację wyłącznie do ustalenia kraju. Nie zapisujemy historii lokalizacji ani dokładnych współrzędnych na backendzie.

### 3.2. Galeria zdjęć

**Cel:** Umożliwienie użytkownikowi ustawienia własnego zdjęcia profilowego.

**Zakres dostępu:**
- Dostęp wyłącznie do zdjęcia wskazanego przez użytkownika.
- Brak potrzeby przeglądania całej galerii.
- Preferowane użycie systemowego selektora zdjęć (Photo Picker).

**Android:**
- Android Photo Picker.
- Nie planujemy READ_MEDIA_IMAGES, jeśli systemowy picker wystarcza.

**iOS:**
- PhotosPicker / PHPickerViewController.
- Brak potrzeby pełnego dostępu do biblioteki zdjęć.

**Moment prośby:** Po kliknięciu "Zmień zdjęcie profilowe" i uruchomieniu systemowego selektora.

**Obsługa odmowy:** Użytkownik może korzystać z domyślnego awatara. Brak zdjęcia profilowego nie blokuje korzystania z aplikacji.

**Minimalizacja danych:** Aplikacja przetwarza wyłącznie wybrane zdjęcie. Nie odczytuje innych fotografii. Zdjęcie profilowe może zostać przesłane na backend po zatwierdzeniu przez użytkownika.

### 3.3. Kamera

**Cel:** Skanowanie kodów QR umożliwiających szybkie wprowadzenie danych przelewu lub otwarcie odpowiedniej funkcji aplikacji.

**Zakres dostępu:**
- Dostęp do kamery wyłącznie podczas skanowania.
- Brak nagrywania filmów i dźwięku.
- Brak potrzeby dostępu do mikrofonu.
- Brak zapisywania obrazu z kamery.

**Android:**
- CAMERA

**iOS:**
- NSCameraUsageDescription

**Moment prośby:** Po kliknięciu przycisku "Skanuj kod QR".

**Obsługa odmowy:** Aplikacja wyświetla możliwość ręcznego wpisania danych przelewu lub kodu. Przy trwałej odmowie może wyświetlić instrukcję włączenia uprawnienia w ustawieniach systemu.

**Minimalizacja danych:** Przetwarzamy wyłącznie dane odczytane z kodu QR. Nie zapisujemy obrazu kamery.


## 4. Testy odmowy uprawnień

### Test 1 - Odmowa lokalizacji

1. Uruchomić automatyczne wykrywanie waluty.
2. Odmówić dostępu do lokalizacji.
3. Sprawdzić, czy można ręcznie wybrać walutę.
4. Sprawdzić, czy aplikacja działa bez błędów.

**Oczekiwany wynik:** Użytkownik może ręcznie ustawić walutę i korzystać z aplikacji.

### Test 2 - Brak dostępu do galerii

1. Otworzyć edycję profilu.
2. Uruchomić systemowy selektor zdjęć.
3. Anulować wybór zdjęcia.
4. Sprawdzić zachowanie aplikacji.

**Oczekiwany wynik:** Aplikacja zachowuje dotychczasowy awatar i nie wymaga dostępu do całej galerii.

### Test 3 - Odmowa kamery

1. Uruchomić skaner QR.
2. Odmówić dostępu do kamery.
3. Sprawdzić dostępność ręcznego wpisywania danych.
4. Ponownie uruchomić funkcję po cofnięciu uprawnienia w ustawieniach.

**Oczekiwany wynik:** Aplikacja nie zawiesza się, a użytkownik może ręcznie wprowadzić dane.

### Test 4 - Cofnięcie uprawnień

1. Przyznać uprawnienie.
2. Cofnąć je w ustawieniach systemu.
3. Powrócić do aplikacji.
4. Ponownie uruchomić odpowiednią funkcję.

**Oczekiwany wynik:** Aplikacja poprawnie wykrywa zmianę uprawnienia i udostępnia alternatywę.

## 5. Dane przechowywane lokalnie

| Dane | Miejsce przechowywania | Poziom wrażliwości | Zabezpieczenie |
|---|---|---|---|
| Token sesji | Bezpieczny magazyn systemowy | Poufne | Android Keystore / iOS Keychain |
| Preferencje użytkownika | Pamięć aplikacji | Wewnętrzne | Izolacja danych aplikacji |
| Wybrana waluta | Pamięć aplikacji | Wewnętrzne | Lokalny zapis ustawień |
| Wybrany kraj | Pamięć aplikacji | Wewnętrzne | Lokalny zapis ustawień |
| Zdjęcie profilowe | Tymczasowo na urządzeniu; docelowo backend | Dane osobowe | Dostęp ograniczony do aplikacji, bez zbędnych kopii |
| Dane zeskanowanego QR | Pamięć operacyjna podczas przetwarzania | Potencjalnie poufne | Walidacja danych |


