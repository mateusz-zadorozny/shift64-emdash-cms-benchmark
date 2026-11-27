---
title: "EmDash 1.3–1.6: co przegapiliśmy i jak poszła aktualizacja emdashcms.pl z 1.2"
slug: emdash-1-3-do-1-6-aktualizacja
excerpt: "Cztery wydania (plus poprawkowe 1.3.1) w niecałe sześć tygodni: pełny polski panel, mniej zapytań do D1, współedycja w czasie rzeczywistym i obrazki w cache na rok. Przejrzałem changelogi pod kątem Cloudflare Workers i D1, a potem zaktualizowałem tę stronę z 1.2 prosto do 1.6 i zmierzyłem różnicę."
tags: [emdash, cloudflare, astro]
status: SZKIC
---

W poście o [EmDash 1.2](/posts/emdash-1-2-smaczki-i-co-w-1-3) zajrzałem do kolejki 1.3 i obiecałem wrócić. Wróciłem z opóźnieniem: w międzyczasie wyszły 1.3 (15 października), 1.3.1 (18 października), 1.4 (29 października), 1.5 (11 listopada) i 1.6 (22 listopada). Zamiast czterech osobnych wpisów — jeden przegląd, ułożony tak jak poprzednio: najpierw najważniejsze w skrócie, potem drobiazgi, które mają znaczenie na Cloudflare Workers i D1, a na końcu aktualizacja tej strony z pomiarami przed i po.

## W skrócie

- **1.3 — polski panel i edycja wizualna.** Panel jest wreszcie w całości po polsku, a edycja na stronie dostała ten sam pasek narzędzi i menu „/” co edytor w panelu.
- **1.4 — mniej zapytań przy bylines.** Autorzy wczytują się z zapytania o treść, a nie osobnymi zapytaniami. Do tego `admin.hiddenNavItems` do ukrywania nieużywanych części panelu.
- **1.5 — praca zespołowa.** Współedycja w czasie rzeczywistym (opcjonalna), pełniejsza historia wersji, tryb staging dla nowych stron, własny serwer SMTP. Do tego kolejna porcja zapytań mniej na każdej stronie.
- **1.6 — cache i wyszukiwarka.** Obrazki w cache na rok (z kompatybilnym providerem), krótki cache dla 404, szybsze wyszukiwanie na D1, zaplanowane wpisy publikowane co do sekundy.

## 1.3: polski panel i poprawki pod D1

Najważniejsza rzecz dla polskich użytkowników: **komplet tłumaczeń panelu** (#3970). W 1.2 dwie trzecie tekstów (2255 z 3384) spadało do angielskiego.

Pod maską, z myślą o D1:

- `getComments()` robi jedno zapytanie zamiast dwóch, gdy zatwierdzone komentarze mieszczą się na jednej stronie (#3907). To była moja [zgłoszona pułapka](https://github.com/emdash-cms/emdash/issues/3905).
- Strony z sesją D1 (`session: "auto"`) i bez `coalesce` nie czekają już w kolejce na prefetch menu i widżetów (#3937). Na tej stronie sesje wyłączyłem już w październiku właśnie z tego powodu.
- Utworzenie szkicu nie czyści cache'u stron (#4128), a nieudany purge nie zgłasza błędu zapisu (#3987).
- `emdash migrate --take-over-lock` (#4068) i wznawialna migracja dat (#4072) — dla dużych baz D1.
- Ostrzeżenie przy buildzie, gdy `emdash` i `@emdash-cms/cloudflare` mają różne wersje (#4058).

**1.3.1** to wydanie poprawkowe, ale z dwiema ważnymi rzeczami dla Workers: strona nie zwraca już 200 bez treści po aktualizacji, której migracji request nie zdążył dokończyć (#4069), a strony z kategoriami nie wiszą z błędem 524 dla wszystkich na izolacie, gdy jeden odwiedzający rozłączył się w trakcie ładowania taksonomii (#4203). Do tego mniej zapytań w wyszukiwarce (#4220).

## 1.4: bylines bez dodatkowych zapytań

Pamiętacie [pole minowe bylines](/posts/emdash-vs-wordpress-rewanz)? Wpis z autorem, ale bez jawnego bylinu, kosztował dwa dodatkowe zapytania, a samo zdefiniowanie pól niestandardowych bylinu — nawet pustych — od czterech do siedmiu na stronę. Od 1.4 bylines rozwiązują się z samego zapytania o treść, a wartości pól ładują się w jednym batchu (#4167). W 1.5 doszły kolejne dwie poprawki (#4631, #4727), więc ta pułapka praktycznie zniknęła.

Inne:

- `admin.hiddenNavItems` (#3856) chowa z menu np. komentarze czy przekierowania, jeśli ich nie używasz.
- Strony z cache hints nie wysyłają już automatycznego `Last-Modified` (#4243), więc Cloudflare przestaje odpowiadać `304` na podstawie daty wpisu, która nie obejmuje zmian w listach i ustawieniach.
- Dwa równoczesne zapisy tego samego wpisu na tej samej wersji dają teraz `409 Conflict` zamiast cichego nadpisania (#4286).
- Przy logowaniu przez Cloudflare Access sesja nie zapisuje się do KV przy każdym żądaniu (#4157) — wcześniej mogło to wyczerpać darmowy limit zapisów.

## 1.5: współedycja i mniej round tripów

Najgłośniejsza nowość to **współedycja w czasie rzeczywistym** (#4695): kilka osób w jednym wpisie, awatary, kursory, scalanie zmian w rich texcie bez nadpisywania. Technicznie: Yjs przez WebSockety, a na Cloudflare każdy otwarty wpis to Durable Object z SQLite (`EmDashRoom`). Jest wyłączona domyślnie; włączasz ją `coEditing: true`, a istniejąca strona na Cloudflare potrzebuje jeszcze bindingu Durable Objects w `wrangler.jsonc` i eksportu klas w workerze.

<details>
<summary>Co współedycja zmienia w pracy zespołu redakcyjnego</summary>

Tu skupiam się na technice i changelogu. O tym, kogo w firmie współedycja dotyczy najbardziej (copywriter i SEO w jednym wpisie, historia zmian dla działu prawnego, staging dla agencji) i czego 1.5 jeszcze nie załatwia, napisaliśmy na naszej drugiej stronie: [EmDash 1.5: koniec z kolejką do wpisu](https://emdash.pl/posts/emdash-1-5-praca-zespolowa?utm_source=emdashcms.pl&utm_medium=post-body&utm_campaign=blog).

</details>

Na tej stronie współedycji nie włączyłem: piszę sam, a to dodatkowy Durable Object i zmiany w workerze bez żadnej korzyści.

Ciekawsze dla mnie były drobiazgi:

- **Zapytanie mniej przy bylines** (#4727) — zniknęło osobne sprawdzanie wersji schematu pól bylinu.
- **Wpis bez tagów nie odpytuje tagów drugi raz** (#4088). To druga z moich pułapek ([#3904](https://github.com/emdash-cms/emdash/issues/3904)), naprawiona m.in. moim PR-em.
- **Zimny start bez osobnego sprawdzania migracji** (#4172) — liczba migracji czyta się w tym samym batchu co reszta danych startowych.
- **Anonimowe strony nie czytają session store** (#4726). Przy sesjach w KV to jeden odczyt KV mniej na każdym niecache'owanym renderze.
- **Krótszy cron** (#4560) — publikacja zaplanowanych wpisów pomija kolekcje, w których nic nie czeka. Ważne przy 10 ms CPU na planie Free.
- **Backupy pod limitem 50 MB** (#4610) — od 4 listopada D1 odrzuca większe wyniki zapytań.
- **Tryb staging** (#3716) dla nowych stron: noindex do momentu publikacji. Istniejących stron nie dotyczy: po aktualizacji emdashcms.pl nie dostał ani `noindex`, ani `X-Robots-Tag`.
- **SMTP** (#2156) — maile systemowe przez dowolny serwer SMTP, także na Workers z `nodejs_compat`.

## 1.6: obrazki na rok i 404 w cache

- **Obrazki w cache na rok** (#4911) — oryginały z `/_emdash/api/media/file/` i warianty z `/_image` dostają tag i długi TTL, a podmiana obrazka czyści cache. Działa z providerem zgodnym z `cacheCloudflare()`. Na tej stronie się nie włączył: mam własny provider, który nie ustawia nagłówków, a cache HTML trzyma Worker.
- **404 z cache przez 60 sekund** (#4992) zamiast renderu przy każdym żądaniu, a opublikowanie brakującego wpisu czyści zapisaną 404 (#4994).
- **Zimny izolat nie zwalnia już blokad crona wtyczek zapisem do bazy** (#4999), więc pierwsze anonimowe wejście nie idzie z tego powodu do primary.
- **Deduplikacja `getEmDashEntry()`** w obrębie żądania (#4926) — uwaga: identyczne wywołania zwracają ten sam obiekt, więc nie modyfikuj go w miejscu.
- **Zaplanowane wpisy punktualnie** (#4787) zamiast do minuty po czasie.
- Szybsze wyszukiwanie i autocomplete na D1 (#4760, #5010) oraz lepsze rankingi (#4194).

## Aktualizacja emdashcms.pl: 1.2.0 → 1.6.0

### Co nie zadziałało od razu

`npx upgrade-emdash@latest` tym razem się wyłożył: npm zgłosił konflikt zależności i przywrócił poprzedni stan. Przyczyną był `@cloudflare/kumo` przypięty w lockfile do wersji 2.6.0 przez paczki 1.2, podczas gdy adapter 1.6 chce dokładnie 2.19.0. Pomogło usunięcie z `package-lock.json` wpisów `emdash`, `@emdash-cms/*` i `@cloudflare/kumo` i ponowne `npm install` z nowymi wersjami wszystkich czterech paczek naraz (rdzeń, adapter i dwie wtyczki). Skutek uboczny: upgrader nie wygenerował `.emdash/UPGRADE.md`, więc changelog przeglądałem ręcznie.

### Migracje i rollback

Od 1.2 doszło siedem migracji (092–098): opcje KV wtyczek, sprzątanie osieroconych pozycji menu, przeindeksowanie użycia mediów, unikalny zakres w storage wtyczek, rodzaj rewizji i lista edytorów, storage pokoi współedycji i data ostatniego logowania. Na planie Free nie puszczałem ich automatycznie przy pierwszym żądaniu: limit 50 zapytań i 10 ms CPU na żądanie raczej by na to nie pozwolił, a release notes 1.5 przy migracji opcji KV wtyczek (#4277) wprost piszą, że wymaga skoordynowanej aktualizacji i nie da się jej wdrożyć stopniowo. Zalecana procedura to zatrzymać wszystko, co pisze do bazy, i dopiero wtedy migrować. Ja strony nie wyłączałem: pisze do niej tylko panel (którego w tym czasie nikt nie używał) i formularz komentarzy. Przy stronie z kilkoma redaktorami warto jednak zrobić to porządnie. Kolejność: bookmark D1 (`wrangler d1 time-travel info`), potem `emdash migrate` z mojego komputera przez API Cloudflare, a dopiero na końcu deploy Workera.

Sprawdziłem lokalnie, że kod 1.2 działa na bazie po migracjach 1.6 — rollback samego Workera jest więc możliwy bez cofania bazy.

### Zapytania na stronę (lokalnie, kopia produkcyjnej bazy, 20 ms opóźnienia na zapytanie)

| Strona | 1.2: zapytania | 1.6: zapytania | 1.2: nagłówki | 1.6: nagłówki |
|---|---|---|---|---|
| Strona główna | 5 | 4 | 76 ms | 59 ms |
| Lista wpisów | 5 | 4 | 77 ms | 58 ms |
| Wpis | 8 | 7 | 98 ms | 76 ms |
| Kategoria | 7 | 6 | 53 ms | 53 ms |

Lokalnie mierzyłem kategorię „Porównania”, a na produkcji (niżej) „Technologię”, stąd 7 zapytań tu i 8 tam.

Zniknęły: odczyt `byline_fields_version` (#4727), drugie zapytanie o tagi (#4088) i drugie o komentarze (#3907). Doszło jedno: przed zapisem strony do route cache EmDash sprawdza, czy reguły przekierowań i ustawienia strony są aktualne (#3997, #4226). Bilans: jedno zapytanie mniej i o jeden krok krótszy łańcuch zapytań sekwencyjnych.

Pułapka przy pomiarze: pierwsze żądanie po migracji publikuje skompilowane reguły przekierowań w tle. Jeśli proces zostanie zatrzymany wcześniej, blokada naprawy trzyma się 60 sekund i przez ten czas każdy render czyta całą tabelę przekierowań — moje pierwsze pomiary pokazały przez to 1.6 jako wolniejsze.

### Produkcja

Mediany z 10 niecache'owanych żądań na stronę (przerwa 1,5 s, nagłówek `Accept` jak z przeglądarki). „Przed” to pomiar 1.2 z 15 października, „po” to 27 listopada, zaraz po deployu — te same strony.

| Strona | Zapytania 1.2 → 1.6 | Render 1.2 → 1.6 | TTFB 1.2 → 1.6 |
|---|---|---|---|
| Strona główna | 5 → 4 | 108 → 90 ms | 380 → 330 ms |
| Lista wpisów | 5 → 4 | 95 → 88 ms | 337 → 313 ms |
| Wpis | 8 → 7 | 122 → 82 ms | 403 → 313 ms |
| Kategoria | 8 → 6 | 101 → 76 ms | 362 → 332 ms |

Przy aktualizacji do 1.2 różnice mieściły się w przedziale od −7 do +14 ms i uznałem je za szum. Tym razem wszystkie cztery strony są szybsze, wpis o 40 ms, a kategoria o 25 ms, i każda robi o jedno lub dwa zapytania mniej. Te dwa pomiary dzieli jednak sześć tygodni, a w październiku żądania szły przez Hamburg, w listopadzie przez Warszawę. Różnica TTFB to więc nie tylko EmDash. Bardziej miarodajny jest render, a całość traktuję jako kierunek, nie dokładną liczbę.

To są renderowania z pominięciem cache. Zwykły czytelnik dostaje stronę z cache Workera (HIT), więc tych liczb zwykle nie widzi.

Po deployu skrypt rozgrzał cache: 41 adresów z sitemapy, jeden co 1,5 s, wszystkie 200. Czas pierwszego (niecache'owanego) wejścia: mediana ok. 210 ms, od 126 ms (tag) do 509 ms.

## Czy aktualizować?

Tak, jeśli jesteś na 1.2. 1.2 nie zmieniało szybkości. 1.6 to pierwsza aktualizacja od dłuższego czasu, która na tej stronie realnie zdejmuje zapytania z każdej niecache'owanej strony. Do tego dochodzi polski panel i poprawki, które na Workers chronią przed pustą stroną po migracji.

Zanim zaczniesz, sprawdź cztery rzeczy:

1. **Migracje na planie Free.** Uruchom `emdash migrate` z własnego komputera przed deployem Workera. Potrzebujesz tokena API z uprawnieniem D1:Edit i ID konta z `npx wrangler whoami`. Nie zostawiaj migracji pierwszemu żądaniu. Płatny plan nie jest do tego potrzebny, bo komenda nie idzie przez Workera.
2. **Lockfile.** Jeśli `upgrade-emdash` zgłosi konflikt z `@cloudflare/kumo`, usuń te paczki z lockfile i zainstaluj wszystkie paczki EmDasha naraz.
3. **Cache.** Jeśli masz własny cache HTML, jak tutaj, sprawdź, czy nie dubluje czyszczenia przy komentarzach. Od 1.5 EmDash sam zgłasza zatwierdzone komentarze do providera cache.
4. **Cron.** Zaplanowane wpisy publikuje cron. Jeśli go wyłączyłeś, tak jak ja na planie Free, zaplanowane wpisy się nie opublikują, nawet z punktualnością z 1.6.

Współedycji nie włączaj „bo jest”. Ma sens dopiero wtedy, gdy nad jednym wpisem pracuje kilka osób.

O tym, czy EmDash nie powinien w ogóle siedzieć w Durable Object, jak w eksperymencie Kevina Kyburza, piszę osobno: [EmDash w Durable Object: 10× szybciej u Kevina Kyburza. Dlaczego zostaję przy D1](/posts/emdash-durable-object-czy-d1).
