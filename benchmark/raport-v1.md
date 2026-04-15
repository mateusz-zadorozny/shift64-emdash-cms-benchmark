# EmDash (Cloudflare Workers) vs WordPress — Raport TTFB

## Metodologia

| Parametr | Wartość |
|----------|---------|
| Okres testowy | 2026-04-03T16:30 → 2026-04-03T20:00 UTC (3.5h) |
| Liczba runów | 22 (co 10 min) |
| Pomiarów łącznie | 572 (286 per site) |
| Testowanych stron | 13 (homepage + 12 postów, identyczny content) |
| Narzędzie | `curl` z pełnym breakdown timingów |
| Lokalizacja testu | Serwer OVH (Warszawa) |
| Izolacja | Każdy URL = nowy curl process (brak keep-alive, brak cache) |
| Kolejność | Randomizowana w każdym runie (eliminacja biasu DNS cache) |

### Testowane strony

| Strona | EmDash (CF Workers) | WordPress |
|--------|-------------------|-----------|
| **Silnik** | Astro 6 + D1 (SQLite edge) | PHP 8.4 + MySQL |
| **Hosting** | Cloudflare Workers (serverless) | Hetzner (Frankfurt) |
| **CDN** | Cloudflare (natywne) | Cloudflare (proxy) |
| **URL** | emdashcms.pl | emdash.pl |
| **Trasa sieciowa** | OVH Waw → CF Edge (Waw?) → D1 | OVH Waw → CF Proxy → Hetzner Fra (~400 km) |

---

## Wyniki: Server Processing Time

> **Server processing** = TTFB minus DNS/TCP/SSL. Czysta praca serwera — query do bazy, renderowanie HTML. To metryka, która izoluje wydajność backendu od sieci.

| Metryka | CF (EmDash) | WP | Różnica | Kto wygrywa |
|---------|-------------|-----|---------|-------------|
| **Średnia** | 496 ms | 90 ms | +406 ms | **WP** (5.5× szybszy) |
| Mediana | 478 ms | 71 ms | +407 ms | WP |
| Min | 142 ms | 44 ms | +98 ms | WP |
| Max | 1259 ms | 246 ms | +1013 ms | WP |
| P95 | 863 ms | 147 ms | +716 ms | WP |
| P99 | 990 ms | 235 ms | +756 ms | WP |
| Odch. std. | 152 ms | 42 ms | | |
| CV (zmienność) | 30.7% | 46.3% | | **CF** (bardziej stabilny) |

## Wyniki: Total TTFB (perspektywa użytkownika)

> **Total TTFB** = DNS + TCP + SSL + Server. To, co użytkownik faktycznie czeka od kliknięcia do zobaczenia pierwszego bajtu.

| Metryka | CF (EmDash) | WP | Różnica |
|---------|-------------|-----|---------|
| **Średnia** | 550 ms | 142 ms | +408 ms |
| Mediana | 535 ms | 119 ms | +415 ms |
| P95 | 954 ms | 216 ms | +739 ms |
| Max | 1351 ms | 373 ms | +978 ms |

## Rozbicie sieciowe (średnie)

| Faza | CF | WP | Uwaga |
|------|-----|-----|-------|
| DNS | 3 ms | 3 ms | Identyczne (oba za Cloudflare) |
| TCP | 1 ms | 1 ms | Serwer testowy blisko obu |
| SSL | 49 ms | 47 ms | Oba z certyfikatem CF |
| **Server** | **496 ms** | **90 ms** | **Tu jest różnica: D1 vs MySQL** |

## Porównanie per strona

| Strona | CF server | WP server | Δ | Zwycięzca |
|--------|-----------|-----------|---|-----------|
| ai | 609 ms | 78 ms | +531 ms | **WP** (7.8×) |
| architektura | 535 ms | 97 ms | +438 ms | **WP** (5.5×) |
| bezpieczenstwo | 541 ms | 96 ms | +445 ms | **WP** (5.6×) |
| co-to-jest-emdash-cms | 493 ms | 88 ms | +405 ms | **WP** (5.6×) |
| emdash-vs-wordpress | 496 ms | 91 ms | +405 ms | **WP** (5.4×) |
| **Homepage** | 222 ms | 90 ms | +132 ms | **WP** (2.5×) |
| jak-zainstalowac | 555 ms | 99 ms | +456 ms | **WP** (5.6×) |
| migracja | 489 ms | 82 ms | +407 ms | **WP** (6.0×) |
| monetyzacja | 476 ms | 73 ms | +403 ms | **WP** (6.6×) |
| open-source | 549 ms | 90 ms | +459 ms | **WP** (6.1×) |
| przyszlosc | 475 ms | 92 ms | +383 ms | **WP** (5.1×) |
| serverless | 509 ms | 100 ms | +409 ms | **WP** (5.1×) |
| wtyczki | 505 ms | 100 ms | +405 ms | **WP** (5.1×) |

**Wynik: WP 13/13, CF 0/13**

---

## Analiza

### 1. WP jest 5.5× szybszy na server processing

Średnia 90 ms (WP) vs 496 ms (CF). Różnica jest konsystentna na wszystkich 13 testowanych stronach. Nawet **najgorszy** wynik WP (246 ms) jest lepszy niż **najlepszy** wynik CF na stronach z postami (408 ms dla wtyczki).

### 2. Homepage CF jest relatywnie szybki (222 ms)

Homepage CF (222 ms) to jedyna strona poniżej 400 ms. Dlaczego? Homepage pobiera listę postów jednym query. Single post odpytuje D1 wielokrotnie: entry + tags + related posts + widget data. Każdy round-trip do D1 na edge dodaje ~50-100 ms latencji.

### 3. CF jest paradoksalnie bardziej stabilny

CV (coefficient of variation) CF = 30.7%, WP = 46.3%. CF ma **niższy** rozrzut procentowy. Ale to mylące — CF jest stabilnie wolny (odch. std. 152 ms), WP jest mniej przewidywalny procentowo, ale jego odchylenie bezwzględne to tylko 42 ms.

### 4. Cold starty CF istnieją, ale nie dominują

Max spike CF = 1259 ms (prawdopodobnie cold start Worker + D1). Ale P95 = 863 ms, co oznacza, że 95% requestów mieści się poniżej ~860 ms. Cold starty są rzadkie, ale gdy się pojawiają, trwają >1 sekundę.

### 5. Sieć nie jest czynnikiem różnicującym

DNS, TCP i SSL są praktycznie identyczne dla obu stron (oba za Cloudflare proxy). Cała różnica to **server processing** — D1 na edge vs MySQL lokalny.

---

---

## Log zmian eksperymentu

| Data | Zmiana |
|------|--------|
| 2026-04-03 16:30 | Start. Cron `*/10 * * * *` (co 10 min). |
| 2026-04-03 ~20:00 | Zmiana na `0,1,2 * * * *` (burst 3×/h: :00 :01 :02, 58 min przerwa). Cel: wyłapanie cold startów CF — przy */10 Worker nie zdążył zasnąć. :00 = cold, :01/:02 = warm. |

*Raport wygenerowany 2026-04-03. Benchmark w toku.*