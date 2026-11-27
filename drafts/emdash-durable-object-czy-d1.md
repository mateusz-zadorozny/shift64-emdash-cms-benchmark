---
title: "EmDash w Durable Object: 10× szybciej u Kevina Kyburza. Dlaczego zostaję przy D1"
slug: emdash-durable-object-czy-d1
excerpt: "W eksperymencie Kevina Kyburza EmDash razem z bazą trafia do jednego Durable Object, a niecache'owane strony przyspieszają od 2,6 do prawie 10 razy. Porównałem te liczby z pomiarami tej strony. U nas większość tego problemu zniknęła inną drogą, ale dwa pomysły biorę od razu."
tags: [emdash, cloudflare, serverless]
status: SZKIC
---

10 listopada na blogu Kevina Kyburza ukazał się opis eksperymentu pod tytułem [„Up to ten times faster without a cache: EmDash in a Durable Object”](https://kevinkyburz.ch/blog/emdash-durable-object). To najciekawszy tekst o wydajności EmDasha, jaki czytałem od czasu własnych pomiarów. Punkt wyjścia jest ten sam co u mnie: pierwsze, niecache'owane wejście na stronę EmDasha na Cloudflare jest wolne. Rozwiązanie jest jednak zupełnie inne. Przeczytałem tekst z naszymi liczbami obok i sprawdziłem, co to zmienia dla tej strony.

## Na czym polega eksperyment

Standardowy EmDash na Cloudflare to Worker, który renderuje stronę, i baza D1, z którą rozmawia przez sieć. Każde zapytanie to osobna podróż w obie strony, u Kevina około 17 ms.

W eksperymencie podział jest inny:

- **Mały Worker z przodu** sprawdza cache (Workers Cache API) i od razu oddaje stronę, jeśli jest w cache.
- **Przy braku w cache** przekazuje żądanie do Durable Object, osobnego dla każdej strony. W tym obiekcie działa cały EmDash razem z własną bazą SQLite. Zapytania nie wychodzą do sieci, tylko trafiają do bazy w tym samym procesie, więc trwają mikrosekundy, a nie milisekundy.
- **Do bazy** EmDash trafia przez własny dialekt SQL, który kieruje zapytania do `ctx.storage.sql`. Cache czyści własny provider cache. Oba mechanizmy to istniejące punkty rozszerzeń EmDasha, więc sam EmDash pozostał bez zmian.

Kod nie jest opublikowany. Autor zastrzega, że to eksperyment, a nie gotowy adapter. Do EmDasha trafiła za to formalna propozycja: [emdash-cms/emdash#4790](https://github.com/emdash-cms/emdash/pull/4790), z dyskusją w [#4789](https://github.com/emdash-cms/emdash/discussions/4789).

## Liczby i jak je czytać

Mediana niecache'owanych odpowiedzi HTML z Cloudflare Analytics. To dane z produkcji, razem z ruchem botów.

| Strona | D1 | Durable Object | Przyspieszenie |
|---|---|---|---|
| scllauerz.ch | 2837 ms | 291 ms | ~9,7× |
| kevinkyburz.ch | 726 ms | 204 ms | 3,6× |
| linguadash.dev | 1184 ms | 450 ms | 2,6× |

W teście laboratoryjnym (curl z Zurychu, trzy kopie tej samej strony demo) ciepły Worker z D1 odpowiadał w 0,29–0,39 s, a Durable Object w 0,08–0,23 s. Największa różnica wyszła przy zimnym starcie: 1,1–2,4 s na D1 wobec 0,10–0,28 s w Durable Object.

Zanim ktoś zacytuje „10×”, trzy zastrzeżenia, które zresztą są w samym tekście:

- Prawie dziesięciokrotne przyspieszenie dotyczy jednej z trzech stron. Pozostałe przyspieszyły 3,6 i 2,6 raza.
- Okno „przed” to 7 dni, a okno „po” to kilka dni od przeprowadzki.
- Pomiary laboratoryjne szły z Zurychu, a Durable Object stoi w Europie, w jednym miejscu. Dlatego pierwsze niecache'owane wejście z Tokio trwa około 850 ms, a z São Paulo około 940 ms.

## Skąd tam tak duże opóźnienia

Z opisu wychodzą trzy przyczyny, które się sumują:

1. **Dużo zapytań na stronę.** W tekście jest 14–25 zapytań, po około 17 ms każde. Nawet częściowo równoległe dają kilkaset milisekund.
2. **Zimne starty.** Duży bundle EmDasha (tam ok. 5 MB po kompresji), ładowanie modułów i pierwsze zapytanie do D1 dają razem 1,1–2,4 s. Przy małym ruchu Worker potrafił wystygnąć już po około 30 sekundach bez odwiedzin.
3. **Cache nie zawsze pomaga.** Po deployu, po publikacji, na rzadko czytanych stronach i w nowych regionach pierwszy odwiedzający płaci pełny koszt renderu.

Durable Object rozwiązuje pierwszy punkt całkowicie, bo zapytania przestają kosztować podróż przez sieć. Łagodzi też drugi: cały niecache'owany ruch trafia do jednego obiektu, a w testach był on dodatkowo podtrzymywany timerem i alarmem. Timer zniknął 10 listopada i dopiero okaże się, ile bez niego zostaje z tego efektu.

## Jak to wygląda na emdashcms.pl

Tę stronę optymalizowałem inną drogą. Zamiast zabierać bazę bliżej kodu, zmniejszałem liczbę podróży do niej.

- **Mniej zapytań.** Po wyłączeniu D1 sessions, przypisaniu bylines, usunięciu pustych pól bylinów i aktualizacji do EmDasha 1.6 strona robi w medianie 4–7 zapytań (pojedyncze żądania do 16), a nie 14–25. Szczegóły aktualizacji opisałem w [przeglądzie EmDasha 1.3–1.6](/posts/emdash-1-3-do-1-6-aktualizacja).
- **Równolegle, nie po kolei.** W lokalnym pomiarze najdłuższy łańcuch zapytań wykonywanych jedno po drugim to dwa, trzy kroki.
- **Worker blisko bazy.** `placement` w `wrangler.jsonc` stawia Workera w Warszawie, najbliższym znanym mi regionie chmury przy Wiedniu, gdzie stoi baza D1. Lepiej mieć jedno dłuższe połączenie do czytelnika niż kilka dłuższych do bazy.
- **Cache HTML na 7 dni**, czyszczony po zmianach w treści. Większość czytelników dostaje gotową stronę.

Efekt w liczbach z 27 listopada (EmDash 1.6, z pominięciem cache, mediana z 10 żądań):

| Strona | Zapytania | Render | TTFB z Polski |
|---|---|---|---|
| Strona główna | 4 | 90 ms | 330 ms |
| Lista wpisów | 4 | 88 ms | 313 ms |
| Wpis | 7 | 82 ms | 313 ms |
| Kategoria | 6 | 76 ms | 332 ms |

Tych liczb nie da się wprost postawić obok tabeli z tamtego tekstu. Tam jest mediana z Analytics dla całego świata, razem z botami, a ja mam serię 10 żądań z jednego miejsca. Da się porównać dwie rzeczy. Nasz render na D1 (76–90 ms) jest w przedziale samego liczenia strony z tamtego tekstu (64–159 ms), więc po stronie bazy i kodu niewiele brakuje. Cała odpowiedź z Polski (TTFB 313–332 ms) jest jednak na poziomie ciepłego D1 z laboratorium (0,29–0,39 s), a nie Durable Object (0,08–0,23 s). Część tej różnicy to droga do czytelnika i z powrotem, której Durable Object nie zmienia. Ile z niej zjadłby DO u nas, wiedziałbym dopiero po teście.

Czego nie wiem: jak często nasi czytelnicy trafiają na zimny start. W serii 10 żądań p95 TTFB wynosił 490–680 ms dla stron z tabeli (do 850 ms na innym wpisie), więc wolne wejścia się zdarzają. Nie mierzyłem ich jednak osobno i nie umiem powiedzieć, czy to 1 % wejść, czy 10 %.

## Ile by nas to kosztowało

To najważniejsza część, bo w samych liczbach Durable Object wygrywa.

- **Plan.** Ta strona działa na darmowym planie Workers. Koszty w tekście są liczone na planie płatnym: 5 dolarów miesięcznie plus, według szacunku autora (bez rachunku), około 12,50 dolara za trzy strony w pierwszej konfiguracji, ciągle podtrzymywanej. Kosztu po zmianach z 10 listopada w tekście jeszcze nie ma.
- **Utrzymanie.** Własny dialekt SQL, własny provider cache i Worker z przodu trzeba sprawdzać przy każdej aktualizacji EmDasha. Po drodze wyszło kilka pułapek: eksport bazy z tabelami FTS5, wewnętrzne tabele `_cf_` (przez nie migracja się wyłożyła i strona przez 30 s zwracała 200 bez treści), błędną liczbę zapisanych wierszy i brak pełnej obsługi transakcji.
- **Jedno miejsce, jedna kolejka.** Wszystkie niecache'owane żądania jednej strony trafiają do jednego obiektu. W teście obciążeniowym, przy 160 równoczesnych żądaniach, p95 dla kevinkyburz.ch wyniósł 11,4 s. Panel admina dzieli moc z odwiedzającymi.
- **Wtyczki w sandboxie nie działają**, bo ich dostęp do danych jest na sztywno podpięty pod D1. Nas akurat to nie blokuje: formularze i webhook-notifier działają tu jako zwykłe wtyczki, bez sandboxa.
- **Kopie zapasowe.** D1 ma Time Travel, z którego sam korzystam przed każdą migracją. Durable Object ma przywracanie do punktu w czasie (do 30 dni), sprawdzone w eksperymencie na wpisie testowym, a obok działają codzienne eksporty do R2. Pełnego odtworzenia z R2 jeszcze nie testowano.

## Co biorę z tego eksperymentu

1. **Rozgrzewanie cache po deployu.** Deploy zmienia klucz cache, więc każda strona zaczyna od braku w cache. Od tego tygodnia `npm run deploy` po wdrożeniu odwiedza wszystkie 41 adresów z sitemapy, jeden co 1,5 s. Po deployu EmDasha 1.6 pierwsze wejścia trwały w medianie 210 ms (od 126 do 509 ms) Żadna z nich nie była wcześniej w cache, więc koszt pierwszego renderu poniósł skrypt, a nie czytelnicy.
2. **Mierzenie zimnych wejść, a nie tylko ciepłych.** Moje benchmarki dotąd liczyły renderowanie na rozgrzanym Workerze. Ten tekst pokazuje, że najgorsze sekundy siedzą gdzie indziej. Następny pomiar tej strony obejmie pierwsze wejście po przerwie.
3. **Obserwowanie #4790.** Jeśli z tej propozycji powstanie oficjalny adapter, utrzymaniem zajmie się zespół EmDasha, a nie ja. Wtedy przetestuję go na tej stronie.

## Komu polecam Durable Object

Według autora strona, której czytelnicy są w jednym regionie, której strony niezawodnie trzymają się w cache i która rzadko publikuje lub wdraża zmiany, może spokojnie zostać przy D1. Durable Object ma sens, gdy kilka z tych warunków spełnia się naraz:

- strona ma mały ruch, więc Worker często stygnie;
- czytelnicy są rozrzuceni po świecie;
- często publikujesz lub wdrażasz zmiany;
- crawlery często odwiedzają rzadko czytane podstrony;
- strona robi kilkanaście lub więcej zapytań.

U nas spełnia się tylko pierwszy. Czytelnicy są głównie w Polsce, zapytań jest w medianie 4–7, a cache rozgrzewam po deployu. Dlatego zostaję przy D1, ale wracam do tematu, gdy zmierzę zimne wejścia albo gdy Durable Object trafi do EmDasha oficjalnie.

Proste porównanie: D1 to magazyn po drugiej stronie ulicy. W eksperymencie magazyn trafia na zaplecze sklepu, więc sprzedawca nie wychodzi po żaden towar. Ja zostawiłem magazyn tam, gdzie był, ale nauczyłem sprzedawcę brać wszystko w dwóch kursach zamiast w dwudziestu, a najczęściej kupowane rzeczy trzymam na ladzie. Przy dwóch kursach przeprowadzka magazynu daje mniej, niż kosztuje.
