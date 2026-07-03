# E-mailové notifikácie pre komunitné opravy

Tento runbook opisuje, ako nastaviť mailovú časť pre admin notifikácie ku komunitným opravám. GitHub issue ostáva zdroj pravdy: email má admina upozorniť a priviesť ho na presný issue alebo admin stránku, nie nahradiť schvaľovací workflow.

## Odporúčané nastavenie

Použi dve oddelené adresy:

- `bibliografia@sss.sk` ako príjem notifikácií a distribučný zoznam adminov,
- reálnu existujúcu schránku, napríklad `admin@sss.sk`, ako SMTP účet na odosielanie.

Presmerovanie `bibliografia@sss.sk` znamená zoznam adries, ktoré dostanú notifikácie. Websupport podporuje virtuálnu adresu, ktorá všetku prijatú poštu prepošle na zvolené cieľové adresy. To je správny model pre admin distribučný zoznam.

Odosielanie je iná vec. SMTP prihlásenie musí použiť reálne vytvorenú schránku. Pri Websupporte je najjednoduchší a najmenej rizikový režim:

- SMTP login: `admin@sss.sk`,
- From: `Digitálna bibliografia SSS <admin@sss.sk>`,
- Reply-To: `bibliografia@sss.sk`,
- To: `bibliografia@sss.sk`.

Ak má byť v hlavičke From striktne `bibliografia@sss.sk`, treba buď vytvoriť `bibliografia@sss.sk` ako reálnu schránku, alebo najprv overiť, či Websupport dovolí odoslať z tejto adresy po prihlásení ako `admin@sss.sk`. Presmerovanie samo o sebe nemusí stačiť ako identita odosielateľa.

Nepoužívaj doménový kôš ako distribučný zoznam. Websupport ho sám neodporúča pre bežné použitie, pretože zvyšuje spam. BCC pravidlá tiež nie sú vhodné ako primárny mechanizmus notifikácií; používajú sa skôr na audit kópií.

## Websupport parametre

Pre schránku `admin@sss.sk` použi hodnoty z WebAdminu:

- SMTP server: `smtp.m1.websupport.sk`,
- port: `465`,
- bezpečnosť: `SSL/TLS`,
- prihlasovacie meno: `admin@sss.sk`,
- heslo: heslo reálnej schránky.

IMAP a POP3 nie sú potrebné na odosielanie notifikácií. Hodia sa iba vtedy, ak chceš čítať doručenú poštu tejto schránky v mailovom klientovi.

## DNS doručiteľnosť

Doména `sss.sk` má SPF záznam, ktorý zahŕňa Websupport:

```text
v=spf1 a mx include:_spf.m1.websupport.sk ?all
```

To je pre odosielanie cez Websupport SMTP správny základ. Doplniť treba ešte DMARC záznam. Na začiatok stačí monitorovací režim:

```text
_dmarc.sss.sk TXT "v=DMARC1; p=none; rua=mailto:bibliografia@sss.sk; adkim=r; aspf=r"
```

Po niekoľkých týždňoch bez problémov sa dá politika sprísniť na `quarantine` alebo `reject`, ale až keď je jasné, že všetky legitímne odosielacie cesty pre doménu prechádzajú SPF alebo DKIM.

## Produkčná integrácia

Aktuálny errata workflow vytvorí GitHub issue a admin ho schvaľuje cez `/admin/opravy/`. E-mailová vrstva má po vytvorení issue poslať HTML notifikáciu na `bibliografia@sss.sk` s týmito odkazmi:

- presný GitHub issue,
- admin stránka `/admin/opravy/`,
- prípadne detail článku, ktorého sa oprava týka.

Schválenie nemá byť obyčajný GET link v emaile. Mailové klienty a bezpečnostné skenery často prednačítavajú odkazy; destruktívna akcia musí ostať za admin prihlásením a POST akciou na stránke `/admin/opravy/`.

Produkčný kód používa Websupport SMTP priamo z Cloudflare Pages Functions cez Workers TCP sockets. V Cloudflare Pages nastav tieto premenné pre produkčné prostredie:

- `ERRATA_EMAIL_TO` ako text, napríklad `bibliografia@sss.sk`,
- `ERRATA_EMAIL_FROM` ako text, napríklad `Digitalna bibliografia SSS <admin@sss.sk>`,
- `ERRATA_EMAIL_REPLY_TO` ako text, napríklad `bibliografia@sss.sk`,
- `ERRATA_ADMIN_URL` ako text, napríklad `https://bibliografia.sss.sk/admin/opravy/`,
- `ERRATA_SMTP_HOST` ako text, predvolene `smtp.m1.websupport.sk`,
- `ERRATA_SMTP_PORT` ako text, predvolene `465`,
- `ERRATA_SMTP_USERNAME` ako text, napríklad `admin@sss.sk`,
- `ERRATA_SMTP_PASSWORD` ako encrypted secret,
- voliteľne `ERRATA_SMTP_SECURE_TRANSPORT`, predvolene `on`,
- voliteľne `ERRATA_SMTP_HELO_DOMAIN`, predvolene `bibliografia.sss.sk`.

Lokálne sa dajú nastaviť cez helper:

```bash
cp .env.cloudflare-mail.example .env.cloudflare-mail
# doplň CLOUDFLARE_API_TOKEN, CF_PAGES_PROJECT_NAME a ERRATA_SMTP_PASSWORD
scripts/configure_cloudflare_errata_email.sh
```

Ak niektorá povinná mailová hodnota chýba, formulár stále vytvorí GitHub issue, ale email sa preskočí. Ak SMTP odoslanie zlyhá, vytvorené issue sa nezruší; chyba ostane iba v runtime logu.

Heslo schránky patrí iba do Cloudflare secretu alebo do lokálnej necommitovanej `.env`/`.dev.vars` pri teste. Neukladá sa do repozitára ani do klientského kódu.

## Testovanie

Pred nasadením over:

1. SMTP server odpovedá na TLS spojení na porte `465`.
2. SMTP server po `EHLO` ponúka `AUTH`.
3. Doména má SPF záznam zahŕňajúci Websupport.
4. Existuje DMARC záznam aspoň s `p=none`.
5. Autentifikované odoslanie z reálnej schránky doručí testovací mail na `bibliografia@sss.sk`.
6. Každá cieľová adresa v presmerovaní dostane testovací mail.

Neoveruj presmerovanie tým, že pošleš mail z Gmail adresy na `bibliografia@sss.sk`, ak je rovnaký Gmail zároveň cieľom presmerovania. Gmail takéto preposielanie často skryje alebo zahodí ako podozrivé.
