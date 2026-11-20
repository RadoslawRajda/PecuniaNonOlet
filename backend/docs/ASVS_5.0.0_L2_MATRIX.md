# OWASP ASVS 5.0.0 — macierz L2 (backend)

Źródłem identyfikatorów jest oficjalny [CSV OWASP ASVS 5.0.0](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv). Wydanie zawiera 183 wymagania poziomu L2. Lista poniżej jest checklistą do oceny tego backendu; sama obecność identyfikatora nie oznacza zgodności.

## Zasady oceny

- **Potwierdzone** — istnieje dowód w kodzie i aktualny, uruchomiony test lub niezależna weryfikacja.
- **Częściowo** — mechanizm istnieje, ale brakuje części pokrycia albo weryfikacji.
- **Brak** — wymaganie nie jest spełnione.
- **N/D** — wymaganie nie ma zastosowania do aktualnej architektury; uzasadnienie jest obowiązkowe.
- **Nieocenione** — nie ma wystarczającego dowodu. Nie jest to status zaliczenia.

W tej iteracji pełne uruchomienie backendowego pytest jest zablokowane brakiem `pydantic_settings` w dostępnej instalacji Pythona. Dlatego nowe implementacje są opisane w [przeglądzie bezpieczeństwa](SECURITY_REVIEW.md), a nie oznaczone jako zweryfikowana zgodność. N/D przypisano wyłącznie wymaganiom WebRTC (V17): backend nie implementuje połączeń RTC, sygnalizacji ani mediów. Pozostałe kontrole wymagają oceny względem konkretnego wdrożenia i testów.

| ASVS 5.0.0 ID | Status | Dowód / uzasadnienie |
|---|---|---|
| V1.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.2.6 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.2.7 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.2.8 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.2.9 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.6 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.7 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.8 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.9 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.10 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.3.11 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.4.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.4.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V1.5.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.1.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V2.4.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.4.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.4.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.4.6 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.5.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.5.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.7.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V3.7.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.1.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.2.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.3.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.4.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V4.4.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V5.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V5.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V5.4.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V5.4.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V5.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.1.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.2.9 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.2.10 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.2.11 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.2.12 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.4.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.5.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.5.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.5.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.5.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.5.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.6.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.6.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.6.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.8.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.8.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.8.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V6.8.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.1.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.3.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.4.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.4.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.5.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.5.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.6.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V7.6.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V8.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V8.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V8.4.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V9.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V9.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V9.2.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.2.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.3.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.4.6 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.4.7 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.4.8 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.4.9 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.4.10 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.4.11 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.5.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.5.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.5.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.5.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.5.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.6.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.6.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.7.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.7.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V10.7.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.2.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.4.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.4.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.5.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V11.6.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V12.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V12.1.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V12.3.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V12.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V12.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V12.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.2.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.2.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.2.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.3.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.4.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.4.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V13.4.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.2.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V14.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.1.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.1.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.3.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.3.6 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V15.3.7 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.1.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.2.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.2.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.2.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.2.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.2.5 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.3.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.3.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.3.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.3.4 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.4.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.4.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.4.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.5.1 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.5.2 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V16.5.3 (L2) | Nieocenione | Do oceny w pełnym przeglądzie kontroli; brak potwierdzenia w tej iteracji. |
| V17.1.1 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |
| V17.2.1 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |
| V17.2.2 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |
| V17.2.3 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |
| V17.2.4 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |
| V17.3.1 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |
| V17.3.2 (L2) | N/D | Backend nie implementuje WebRTC/DTLS/SRTP; ponownie oceń, jeśli dojdą media czasu rzeczywistego. |

## Zakres i ograniczenia

Macierz zawiera komplet wymagań L2 z wydania 5.0.0, ale statusy „Nieocenione” oznaczają otwartą pracę. Nie wolno raportować backendu jako zgodnego z ASVS L2 na podstawie tej macierzy. Następny krok to ocena każdego wymagania pod kątem API, aplikacji mobilnej i konfiguracji uruchomieniowej, przypisanie dowodów testowych oraz formalne uzasadnienie każdego N/D.

