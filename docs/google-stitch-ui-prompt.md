# Google Stitch / AI UI prompt

Navrhni vizualne doladenie existujuceho webu "Digitálna bibliografia Spravodaj SSS". Nejde o landing page ani marketingovy web. Je to pracovny bibliograficky portal pre badatelov, speleologov a citatelov archivnych clankov. Prva obrazovka ma byt priamo pouzitelna aplikacia: vyhladavanie, filtre, zoznam clankov, detail clanku, citacie a PDF otvorenie v novej karte.

Pouzi len tuto farebnu paletu:
- gainsboro: rgb(229, 227, 227)
- gray: rgb(141, 116, 106)
- darkgray: rgb(160, 163, 165)
- black: rgb(36, 23, 21)
- dimgray: rgb(107, 108, 112)
- lightslategray: rgb(135, 143, 159)
- earth dimgray: rgb(101, 71, 60)
- blue dimgray: rgb(81, 83, 98)
- brown black: rgb(74, 46, 38)
- firebrick: rgb(206, 61, 59)
- warm dimgray: rgb(78, 72, 71)
- peru: rgb(204, 159, 88)

Vizualny smer:
- Tichy, seriozny, archivny a pracovny styl podobny sss.sk, nie moderny SaaS dashboard s modro-fialovymi gradientmi.
- Pozadie webu moze pouzit gainsboro, ale panelove plochy nech su citatelne, kludne s jemnymi hranami v darkgray/lightslategray.
- Firebrick pouzivaj iba na hlavne akcenty, aktivne stavy, linky a primarne tlacidla.
- Peru pouzivaj striedmo na sekundarne akcenty, rocnik/cislo/metadatanadpisy alebo male odlisovacie prvky.
- Text ma byt primarne black alebo brown black, sekundarny text dimgray/warm dimgray/blue dimgray.
- Nepouzivaj mapu, hero sekciu, dekorativne ilustracie, gradient orb pozadia, velke marketingove karty ani auto-nacitany PDF viewer.

Rozlozenie:
- Desktop: zachovaj dvojpanelovy archivny layout. Vlavo hutny zoznam vysledkov s rychlym skenovanim, vpravo detail clanku.
- Mobil: jednoslpcovy tok. Vyhladavanie a filtre hore, vysledky pod tym, detail clanku ako samostatny pohlad alebo kompaktna sekcia.
- Roky, cislo casopisu, strany, autori a nazov musia byt vizualne jasne odlisene.
- Kazdy rocnik ma cisla 1-4; nevytvaraj filter "vsetky cisla".
- PDF sa nikdy nema nacitat automaticky. Ma byt iba jasne tlacidlo "Otvoriť PDF v novej karte".
- Fulltext filter nech je viditelny, ale nie dominantny.

Komponenty, ktore dolad:
- Hlavicka: kompaktna, institucna, s nazvom Slovenska speleologicka spolocnost a kratkym kontextom archivu.
- Vyhladavanie: vysoko pouzitelny input s jasnym focus stavom.
- Filtre: rok rozsah, cisla 1-4, mapy/plany, fulltext. Musia byt kompaktne a citatelne.
- Zoznam clankov: kazda polozka ma mat jasnu hierarchiu: rok/cislo/strany, nazov clanku, autor, kratka anotacia.
- Detail clanku: nazov clanku najvyraznejsi, autor druhy najvyraznejsi, metadata v prehladnom pase, anotacia ako citatelny blok.
- Citacie: ISO 690, APA, MLA ako kopirovatelne bloky bez vizualneho sumu.
- Errata: lokalne komunitne poznamky nech posobia ako pracovny dodatok, nie hlavny obsah.
- Statistiky D3: jednoduche, citatelne, bez farebnej preplnenosti.

Vystup od AI UI asistenta:
1. Navrhni finalny vizualny system v kratkych dizajnovych pravidlach.
2. Daj kompletne CSS/Tailwind odporucania pre farby, spacing, border, hover/focus/active stavy a typografiu.
3. Uved konkretnu upravu hlavnej stranky a detailu clanku.
4. Zachovaj existujucu funkcionalitu, nemen informačnu architekturu mimo vizualneho doladenia.
5. Nepouzivaj farby mimo uvedenej palety, okrem bielej iba pre tlacove exporty, nie ako hlavnu webovu paletu.
