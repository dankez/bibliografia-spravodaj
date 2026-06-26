# Architektúra digitálnej bibliografie SSS

Tento dokument opisuje aktuálnu architektúru portálu pre Spravodaj SSS, Aragonit a Slovenský kras. Stav zodpovedá produkčnému nasadeniu na Cloudflare Pages.

## Ciele

Projekt nie je iba zoznam PDF súborov. Nad článkami vytvára vrstvu metadát, fulltextu, citácií, exportov, registra jaskýň a komunitných opráv.

Hlavné rozhodnutia:

- Verejný web je statický Astro build, aby sa dal lacno hostovať a rýchlo cachovať.
- Produkcia nepoužíva serverovú databázu. Verejné dáta sú JSON, statické stránky a exportné súbory.
- Veľká research SQLite databáza a raw fulltext sa generujú lokálne a necommitujú sa do repozitára.
- PDF dokumenty ostávajú na pôvodných zdrojoch, najmä `sss.sk`, `ssj.sk` a `smopaj.sk`; portál odkazuje na správnu fyzickú PDF stranu.
- Komunitné opravy nejdú priamo do dát. Vždy vznikne GitHub issue, ktoré schvaľuje admin.

## Hlavné vrstvy

### 1. Bibliografické dáta

Primárna článková databáza je uložená v JSON súboroch:

- `data/articles_with_urls.json` pre skripty, exporty a lokálne spracovanie,
- `web/src/data/articles.json` pre frontend build.

Každý článok obsahuje ID, názov, autorov, časopis, rok, ročník, číslo, strany, PDF URL, vypočítanú PDF stranu, anotáciu, tagy, jaskyne, oblastné skupiny a príznaky ako mapa/plán.

### 2. Fulltext a research vrstva

Fulltext sa vytvára lokálne zo zdrojových PDF:

- `scripts/extract_pdf_fulltext.py` extrahuje text článkových rozsahov,
- `scripts/build_research_knowledge_db.py` generuje lokálnu SQLite/FTS databázu,
- `scripts/export_web_fulltext_index.py` pripravuje delený verejný fulltext index pre web.

Research databáza slúži na rešerše, AI sumarizácie a neskoršie redakčné nástroje. Do Gitu sa neukladá, pretože je veľká.

### 3. Webová vrstva

Frontend je v `web/`:

- `web/src/pages/index.astro` hlavný archív,
- `web/src/pages/clanky/[id].astro` detail článku,
- `web/src/pages/clanky/[id]/edit.astro` štruktúrované hlásenie opravy,
- `web/src/pages/jaskyne/index.astro` register jaskýň,
- `web/src/pages/jaskyne/[slug].astro` časová os jaskyne,
- `web/src/pages/admin/opravy.astro` admin schvaľovanie errata.

Vyhľadávanie beží v prehliadači nad statickými dátami. Základné bibliografické vyhľadávanie používa článkový JSON; fulltext je delený podľa časopisu a rokov, aby mobil nemusel sťahovať celý index naraz.

### 4. Cloudflare Pages Functions

Statický web dopĺňajú malé serverové funkcie v `web/functions/`:

- `api/error-report.js` vytvára GitHub issue z verejného hlásenia chyby,
- `api/admin/login.js`, `api/admin/logout.js`, `api/admin/session.js` spravujú admin session,
- `api/admin/errata.js` načíta otvorené errata issues a pri schválení spustí GitHub Actions workflow.

Admin login je jednoduchý heslový režim:

- heslo sa neukladá do repozitára,
- produkcia obsahuje iba `ADMIN_PASSWORD_HASH`,
- session podpisuje `SESSION_SECRET` alebo `ADMIN_SESSION_SECRET`,
- cookie je `HttpOnly`, `Secure` a `SameSite=Strict`.

### 5. GitHub Actions approval workflow

Admin tlačidlo "Schváliť" nerobí priamy zápis veľkých JSON súborov v Cloudflare Function. Namiesto toho spustí:

- `.github/workflows/approve-errata.yml`,
- `scripts/apply_errata_issue.py`.

Workflow:

1. prijme číslo GitHub issue,
2. načíta issue cez GitHub API,
3. vyberie JSON diff so schémou `sss-bibliografia/article-edit/v1`,
4. overí whitelist polí článku,
5. skontroluje, že pôvodné hodnoty v issue stále sedia s aktuálnymi dátami,
6. zapíše zmeny do `data/articles_with_urls.json` a `web/src/data/articles.json`,
7. vytvorí commit do `main`,
8. zavrie issue komentárom s odkazom na commit.

Push do `main` následne spustí Cloudflare Pages deploy.

## Hosting a deploy

Produkčný web beží na Cloudflare Pages:

- build root: `web`,
- build command: `npm run build`,
- output directory: `dist`,
- custom domain: `bibliografia.sss.sk`.

Cloudflare Pages po každom pushe do `main` vytvorí nový statický build. Footer webu zobrazuje release identifikátor s dátumom a commit hashom, aby sa dalo overiť, ktorá verzia je live.

## Dôležité runtime premenné

Produkčné premenné sa nastavujú v Cloudflare Pages, nie v repozitári:

- `PUBLIC_TURNSTILE_SITE_KEY`,
- `TURNSTILE_SECRET_KEY`,
- `GITHUB_REPOSITORY`,
- `GITHUB_TOKEN`,
- `GITHUB_ISSUE_LABELS`,
- `ADMIN_PASSWORD_HASH`,
- `SESSION_SECRET` alebo `ADMIN_SESSION_SECRET`,
- voliteľne `ADMIN_SESSION_SECONDS`,
- voliteľne `ADMIN_USER_LABEL`,
- voliteľne `ADMIN_APPROVAL_WORKFLOW`,
- voliteľne `ADMIN_BASE_BRANCH`.

Tokeny a heslá musia byť nastavené ako secrets. Do Gitu nepatrí `.env` ani reálne hodnoty týchto premenných.

## Exporty

Exporty generujú skripty v `scripts/` do `data/exports/`:

- HTML,
- Markdown,
- PDF,
- SQL/SQLite,
- tlačové čiernobiele HTML.

Exporty môžu byť spoločné pre všetky časopisy alebo samostatné podľa časopisu. Pri samostatnom exporte sa číslovanie článkov začína od 1 pre daný časopis.

## Register jaskýň

Register jaskýň sa generuje z článkových metadát a podporných zoznamov:

- `data/cave_aliases.json` pre ručné aliasy a zlučovanie,
- `data/smopaj_cave_register_2017.json` pre register SMOPaJ,
- `data/geomorphology_regions.json` pre geomorfologické jednotky,
- `scripts/build_cave_index.py` pre výsledný index.

Rovnako pomenované jaskyne sa majú rozlišovať podľa kontextu, oblasti a geomorfologického celku. Niektoré priradenia sú isté, iné ostávajú kurátorské.

## Poznámka k Zotero

V repozitári zostali historické skripty ako `scripts/upload_to_zotero.py`, ale aktuálny produkčný web nepoužíva Zotero ako runtime CMS. Zdrojom produkčného webu sú JSON dáta v repozitári a automatizované buildy.
