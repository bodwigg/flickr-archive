# Flickr-samlingen som "månadens" – brief för nytt repo

Underlag för en ny tråd och ett nytt, fristående repo. Klistra in hela filen i den nya tråden och lägg den i repots rot (t.ex. som `docs/BRIEF.md`).

## 1. Mål

En statisk sida på den egna webbplatsen **ulfbodin.se** som visar min Flickr-samling (8 100 bilder) som en utställningslik djupdykning i en fotografs samling – samma upplägg som "månadens" i Radius (`/<app>/manadens/`), men utan server: all data byggs i förväg och filtreras i webbläsaren.

## 1b. Plats och befintliga sidor

- **Ingång:** [ulfbodin.se/photography.html](https://ulfbodin.se/photography.html) – länkar i dag till Portfolio, Map och Flickr. Den nya sidan läggs till där (t.ex. `ulfbodin.se/archive.html` eller `ulfbodin.se/archive/`).
- **Webbplatsen** är GitHub Pages: repot [bodwigg/bodwigg.github.io](https://github.com/bodwigg/bodwigg.github.io) (publikt, gren `main`, `CNAME` = `ulfbodin.se`). Jekyll med fjärrtemat `liamg/jekyll-theme-abysm` (mörkt), egen `_layouts/page.html`, `_includes/footer.html` och `assets/css/custom.css` (länkfärger `#7aa2f7`, besökt `#bb9af7`, hover `#a0c776`). Sidorna är mest Markdown (`index.md`, `photography.md`, `portfolio.md`, `projects.md`) plus fristående HTML-sidor med egna kartor (`map.html`, `gotland.html`, `skolor.html` m.fl.). Inga GitHub Actions – GitHub bygger Jekyll själv.
- **Publicering av den nya sidan:** ett eget repo (t.ex. `bodwigg/flickr-archive`) med GitHub Pages via Actions hamnar automatiskt på `ulfbodin.se/flickr-archive/`, eftersom projektsidor ärver användarsidans domän. Då behöver bodwigg.github.io bara en länk från `photography.md`. Alternativ: bygget kopierar `dist/` in i bodwigg.github.io (fristående HTML-sida utan Jekyll-layout).
- **Flickr-konto:** [flickr.com/photos/ulfbodin](https://www.flickr.com/photos/ulfbodin/) (användarnamn `ulfbodin`, NSID **`10817753@N03`**).
- **Portfolio (heros):** [ulfbodin.se/portfolio.html](https://ulfbodin.se/portfolio.html) – 32 utvalda bilder i 8 grupper (se avsnitt 4b). De blir hero-listan.
- **Karta:** [ulfbodin.se/map.html](https://ulfbodin.se/map.html) – fristående HTML-sida med Leaflet 1.9.4 + Leaflet.markercluster 1.5.3 (unpkg), OpenStreetMap-kakel, klusterfärg `rgba(255, 0, 132, …)`. Läser `flickr.geojson` (4,4 MB, 6 017 punkter, `bbox` för startvyn) med egenskaperna `id, title, date, date_upload, url, thumbnail (_t), image_source (_s), license, license_url`. **Beslut: map.html ersätts** av den nya sidans kartfilter (map.html blir en hänvisning till `/flickr-archive/`). Det gamla geojson-skriptet (lokalt, skriver till `c:\output\`) ersätts av exportskriptet; se avsnitt 5 för vad som tas med och vilka fel som rättas.
- **Data Lifeboat:** samlingen finns också som [Data Lifeboat-showcase](https://datalifeboat.flickr.org/dl-showcase/Ulf_Bodin-Upsala/README.html) – möjlig alternativ/kompletterande datakälla.

## 2. Samlingen (Flickr-statistik, 2026-11-03)

| | Antal |
|---|---|
| Objekt totalt | 8 097 |
| Foton | 8 090 |
| Videor | 7 (tas inte med) |
| Publika | 6 751 (resten: vänner/familj/privata – tas inte med) |
| I album | 7 594 |
| I grupper | 4 371 (tas inte med – grupper ingår inte) |
| Taggade | 7 471 |
| Geotaggade | 6 749 |
| Visade | 7 734 |
| Favoritmarkerade | 5 886 |
| Kommenterade | 3 534 |
| Lagring | 131 GB (stannar på Flickr – bilderna länkas, kopieras inte) |

Siffrorna gäller hela kontot; bland de publika fotona är andelen taggade, geotaggade och i album okänd tills exporten körts.

**Licens:** främst [CC BY-NC-SA 2.0](https://creativecommons.org/licenses/by-nc-sa/2.0/deed.en), men licenserna varierar. Fördelningen bland de 6 017 geotaggade fotona i `flickr.geojson`:

| Licens | Antal |
|---|---|
| CC BY-NC-SA 2.0 | 4 881 |
| CC BY-NC-ND 2.0 | 625 |
| All Rights Reserved (©) | 289 |
| CC BY-NC-SA 4.0 | 174 |
| CC BY-NC 2.0 | 23 |
| CC BY 2.0 | 21 |
| Public Domain Mark | 2 |
| CC BY-NC 4.0, CC BY-SA 2.0 | 1 vardera |

Licensen ska därför visas per bild i bildvisaren (med länk till licenstexten), finnas som filter (som i "månadens") och sammanfattas i sidfoten. ©-bilder märks tydligt.

## 2b. Sondering mot API:t (2026-11-03)

`python export/flickr_export.py --probe`, stickprov 1 000 foton (500 nyaste + 500 äldsta uppladdade):

| | Resultat |
|---|---|
| Publika foton (`media=photos`) | **6 745** (+ 5 publika videor, tas inte med) |
| Första uppladdning | augusti 2007 |
| `count_faves`, `count_comments` som extras | **Fungerar** (100 %) – inga extra anrop för hero-urvalet. Max 335 favoriter, max 13 006 visningar, median 969 |
| `url_k` (2048 px) | 92,4 % – resten faller tillbaka på `url_l`/`url_c` |
| `url_c` (800 px), `o_dims` | 100 % |
| 1024 px | Heter `url_l` som extra (filsuffix `_b`) – finns för 99,9 % |
| Licenser i stickprovet | CC BY-NC-ND 2.0 382, CC BY-NC-SA 2.0 277, CC BY-NC-SA 4.0 220, © All Rights Reserved 111, CC BY 2.0 7, Public Domain Mark 2, CC BY-NC 4.0 1. De äldsta bilderna är mest BY-NC-ND 2.0, de nyaste BY-NC-SA 4.0 |
| Geotaggade / taggade / med beskrivning | 79,9 % / 95,4 % / 72,5 % |
| Maskintaggar | 0 % |
| Publika album | **205** (11 979 albumplatser – bilder ligger ofta i flera album) |
| EXIF (10 bilder) | Kamera 10/10, objektiv 5/10 – objektiv saknas på kameror med fast objektiv (Sigma DP1, Olympus C5060WZ) |

**Album av olika slag.** De största albumen är både platser (Uppsala 901, Stockholm 757) och utrustning (Canon EOS 5D Mark II 1 271, Sigma DP1 611, Canon EF 24 mm f/1,4 L II USM 416). Albumen bör därför delas upp i typer (plats, utrustning, tema …) i en konfigurationsfil, så att utrustningsalbum kan ligga under kamera/objektiv i stället för "Varför". Fast objektiv kan fyllas i per kameramodell.

## 3. Beslut

- **Eget repo `bodwigg/flickr-archive`**, skilt från Radius och från bodwigg.github.io. Adress: **`ulfbodin.se/flickr-archive/`**. bodwigg.github.io får bara en länk i `photography.md`. Ingen kod delas via import – filer kopieras och anpassas.
- **Publikt repo** (som bodwigg.github.io). Pages från privata repon kräver GitHub Pro och sajten blir ändå publik; Actions är gratis utan gräns i publika repon. Det enda hemliga är API-nyckeln, som ligger som Actions-secret.
- **Statisk sida** via GitHub Pages med Actions (Pages-källa: "GitHub Actions"), se avsnitt 1b.
- **Form:** "månadens" layout och funktioner, men med ulfbodin.se:s mörka bakgrund (se avsnitt 6b).
- **Bara publika foton** (`privacy_filter=1`, `media=photos`). Foton som bara är synliga för vänner/familj eller privata hämtas aldrig.
- **Album ingår, grupper inte.** Album (photosets) blir "Varför"-dimensionen och egna rader på sidan. Gruppdata hämtas inte alls (inga `flickr.groups.*`- eller `getAllContexts`-anrop).
- **Bara publika album** visas; bilder i album som inte är publika räknas inte.
- **Bilderna laddas från Flickrs CDN** (`live.staticflickr.com`), aldrig in i repot. Varje bild länkar tillbaka till sin Flickr-sida (Flickrs villkor).
- **Uppdatering:** schemalagt GitHub Actions-jobb i det nya repot (Flickr-nyckeln som secret) kör exporten, bygger och publicerar till Pages. Kan även köras för hand. Jobbet committar `data/*.json` när något ändrats – det håller schemat vid liv (GitHub stänger av scheman efter 60 dagar utan aktivitet) och sparar läget för inkrementell export.

## 4. Upplägget – från Radius "månadens" till Flickr

| Radius "månadens" (KulturNav + DigitaltMuseum) | Flickr-versionen |
|---|---|
| Stor bild överst (hero), dagens urval + `hero.json` | Mest visade / mest favoritmarkerade (views, faves) som grund; `hero.json` för handplockade, fylls på med slumpbilder |
| Personen i några rader (KulturNav-posten) | Profiltext + egen text i en konfigurationsfil |
| Ett liv i bilder – tidslinje år för år | `date_taken` per år (ev. per månad) |
| Teman (vanligaste ämnesorden) | Vanligaste taggarna (normaliserade, utan maskintaggar) |
| Uppdrag (uppdragsnummer i titeln) | Album (photosets) |
| Arkivet – bildvägg med filter När/Var/Vad/Varför | Samma: När = datum, Var = karta + orter, Vad = taggar, Varför = album |
| Museer och licenser i sidfoten | Licenser; ev. kamera/objektiv (EXIF) som eget filter |
| Bildvisare med uppgifter + DigitaltMuseum-länk | Titel, beskrivning, datum, taggar, plats, licens + länk till Flickr |
| Djupzoom (IIIF + OpenSeadragon) | OpenSeadragon med en enkel bildkälla (största tillgängliga storlek, t.ex. `_k` 2048 px) |

## 4b. Hero-listan (från portfolio.html)

32 bilder i åtta grupper. Grupperna kan också användas som handplockade "teman" överst bland teman. Liggande bilder (panoramorna) visas i helbredd, stående och kvadratiska hela bredvid texten.

| Grupp | Flickr-id |
|---|---|
| Golden | 11239519916, 40883074782, 35708560543, 26101191820 |
| Blue | 33621814458, 12466398273, 10057700646, 47555010411 |
| Street | 8868855162, 13742758993, 40250193834, 52545396685 |
| Urban | 8032992185, 14098647474, 53364475681, 32568302341 |
| Panorama | 22229082528, 48615761886, 14667467440, 16045369985 |
| Black & White | 22583841975, 15490937218, 55283045818, 54795581298 |
| Model | 48585906931, 48220646277, 48585905811, 14721489097 |
| Portrait | 55062529228, 48094086612, 51381649122, 48672630206 |

Obs: på portfolio.html länkar bilden "Assi, June 8, 2014" (bild 14721489097) till Flickr-sidan för 54795581298 (Friseboda) – troligen fel länk.

## 5. Arkitektur

```
flickr-export (Python, lokalt eller i Actions)
  └─ data/photos.json        alla publika foton, kompakt (~1 MB, ~300 kB gzip)
  └─ data/albums.json        album med titel, beskrivning, foto-id:n
  └─ data/details/xx.json    beskrivningar m.m. uppdelat på id-prefix, hämtas vid behov
build (Python + Jinja2)
  └─ dist/index.html         färdig HTML: hero, presentation, tidslinje, teman, album
  └─ dist/static/…           css, js, vendor/openseadragon
webbläsaren
  └─ laddar photos.json, filtrerar/räknar/söker lokalt (bildväggen, filterpanelerna, kartan)
```

### Flickr API

- `flickr.people.getPhotos` (eller `getPublicPhotos`), `per_page=500`, med `extras`:
  `description, license, date_upload, date_taken, last_update, geo, tags, o_dims, views, media, path_alias, count_faves, count_comments, url_q, url_n, url_w, url_c, url_l, url_k`
  (`count_faves`/`count_comments` fungerar, se 2b; `url_l` = 1024 px).
- `flickr.photosets.getList` + `flickr.photosets.getPhotos` för albumen (`privacy_filter=1`; bara foton som också finns i den publika exporten behålls).
- Inga gruppanrop.
- Valfritt: `flickr.photos.getExif` för kamera/objektiv (ett anrop per bild – körs inkrementellt och cachas).
- Bild-URL: `https://live.staticflickr.com/{server}/{id}_{secret}_{storlek}.jpg` – storlekar `q` 150 (kvadrat), `n` 320, `w` 400, `c` 800, `b` 1024, `k` 2048 (`k` har egen secret – ta URL:en från `url_k`).
- Inkrementell uppdatering: `min_upload_date` / `last_update` jämfört med föregående körning.

### Lärdomar från det gamla geojson-skriptet

- Behåll: `flickr.photos.search` med `user_id`, uppdelat på uppladdningsdatum (sökningen ger högst ~4 000 träffar per fråga); licenslistan hämtas från `flickr.photos.licenses.getInfo`. Anrop med bara API-nyckel ger enbart publika foton.
- Rätta: skriptet hämtade bara första sidan (500) per halvår och bläddrade aldrig vidare – första halvåret 2013 (402 geotaggade) slog sannolikt i taket, 2012 H1 (346) ligger nära. Intervallen lämnade glapp (23:59–00:00 vid halvårsskiftena). `dateupload` kunde ärvas från föregående bild.
- Nytt: paginering med `page`/`pages`, tidsintervall utan glapp (`max_upload_date` = nästa intervalls start − 1 s, i UTC), alla extras i ett anrop, nyckel från `.env`.

### Hemligheter

- `FLICKR_API_KEY` (och ev. secret) i `.env` lokalt och som GitHub Actions-secret – aldrig i kod, chatt, webbläsare eller loggar. Behövs bara i exportsteget, inte på sajten.
- NSID `10817753@N03` står öppet i konfigurationen (inte hemligt).
- **Den gamla API-nyckeln ska roteras** – den låg i klartext i geojson-skriptet och har visats i en chatt. Ny nyckel bara i `.env` och som Actions-secret.

## 6. Att ta med från Radius

Kopiera och anpassa från Radius-repot (läget 2026-11-03):

- `static/featured.css` – hela formspråket: palett som CSS-variabler (`--bg`, `--accent`, `--shade` …), hero, tidslinje, teman, uppdrag, bildvägg, filterpaneler, bildvisare, sidfot, mobil.
- `static/featured.js` – gränssnittet. Anropen till `/api/images`, `/api/facets`, `/api/geo`, `/api/image/{id}` ersätts med lokal filtrering mot `photos.json`; logiken i `core/featured_app.py` (`_filters`, `_wall`, `_facets`) skrivs om i JavaScript.
- `templates/featured.html` – Jinja-mallen, renderas i byggsteget i stället för per anrop.
- `core/featured_i18n.py` – bara de engelska texterna (sidan är enspråkig).
- `static/vendor/openseadragon/` och `static/vendor/leaflet*` (kartan).

Funktioner som redan finns och ska följa med:

- Hero med lat inläsning (bara nästa bild laddas), växling var 9:e sekund, dagligt urval; handplockade bilder först (`hero.json`) och sedan slumpbilder.
- Kvadratiska/stående bilder visas hela bredvid texten i heron (`featured_hero_whole`), liggande i helbredd.
- Centrerad presentation på breda skärmar.
- Tidslinje med stora pilar fram/bak.
- Val av år, tema eller album nollställer arkivets filter; den klickade bilden läggs först i arkivet med en pulserande ram som tonar bort efter ~5 s.
- Filterpanelen scrollas in i bild när den öppnas långt ner i bildväggen; på små skärmar stängs panelen efter ett val.
- Bildväggen fyller på själv 4 sidor à 60 bilder, sedan knappen "Visa fler" – så att sidfoten (Om) går att nå. Om-länken i menyn pausar påfyllningen.
- Kronologiskt stigande/fallande (klick på vald knapp vänder, pil ↑/↓), Blandat.
- Albumraderna fylls med upp till 20 bilder, men bara de som får plats laddas.
- Bokmärken (IndexedDB), djupzoom. **Inget språkval** – sidan är bara på engelska.
- Typsnitt: samma som ulfbodin.se (systemtypsnitt), se avsnitt 6b.

## 6b. Färger (ulfbodin.se)

"månadens" palett (CSS-variablerna i `featured.css`) byts mot webbplatsens mörka tema:

| Roll | Värde | Källa |
|---|---|---|
| Bakgrund | `#202030` | abysm `$background` |
| Text | `#dddddd` | abysm `$foreground` |
| Ljus text/rubriker | `#ffffff` | abysm `$bright` |
| Dämpat (linjer, metadata) | `#444466` | abysm `$dim` |
| Länk | `#7aa2f7` | `custom.css` |
| Länk, besökt | `#bb9af7` | `custom.css` |
| Länk, hover / accent | `#a0c776` | `custom.css` |
| Bildram | `rgba(255,255,255,.12)`, rundning 12 px | `custom.css` (.photo-card) |

Typsnitt: samma som webbplatsen – abysm:s systemtypsnitt (`-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif`). Fraunces/Inter från "månadens" tas inte med; kan omprövas när sidan går att se.

## 7. Arbetssätt (gäller också nya tråden)

- Svar på svenska.
- Python med tabbar, inte mellanslag.
- CRLF-radslut i filerna.
- Ändringar testas lokalt (Playwright) innan de lämnas över.

## 8. Besvarade frågor (2026-11-03)

| Fråga | Beslut |
|---|---|
| Repo och adress | `bodwigg/flickr-archive` → `ulfbodin.se/flickr-archive/` |
| Sidans titel | **Ulf Bodin – Photography** |
| Språk | Bara engelska – inget språkval |
| Det gamla geojson-skriptet | Inklistrat i tråden; ersätts av exportskriptet (avsnitt 5) |
| map.html | Ersätts av den nya sidans kartfilter |
| Hero | Portfolio-listan (avsnitt 4b) först, sedan slump bland mest visade/favoritmarkerade |
| ©-bilder | Tas med och märks tydligt ("© All rights reserved") i bildvisaren och som licensfilter |
| Kamera/objektiv (EXIF) | Ja, om det går – `flickr.photos.getExif` per bild (~6 750 anrop, knappt 2 h första gången), cachas och körs sedan bara på nya/ändrade bilder |
| Färger | "månadens" form med ulfbodin.se:s mörka palett (avsnitt 6b) |
| Typsnitt | Samma som webbplatsen (systemtypsnitt) tills vidare |

Mätt vid sonderingen – se avsnitt 2b.

## 9. Första steg i nya tråden

1. Skapa det nya repot med mappstruktur (`export/`, `build/`, `site/` eller liknande), `.env.example`, `.gitignore`.
2. Exportskript mot Flickr API → `data/photos.json` + `data/albums.json`; kör lokalt och kontrollera siffrorna mot tabellen ovan.
3. Byggsteg med Jinja2 → `dist/`.
4. Porta `featured.js` till lokal filtrering; testa med Playwright.
5. GitHub Actions: schemalagd export + bygge + publicering till Pages.
