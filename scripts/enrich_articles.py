#!/usr/bin/env python3
"""
Enrich Articles Script
Scans article titles and abstracts to add semantic tags, cave names,
associated SSS speleological groups, and Wikidata references.
"""

import os
import json
import re

from build_cave_index import article_mentions_cave

# Major Slovak Caves coordinates and metadata
MAJOR_CAVES = [
    {"name": "Demänovské jaskyne", "keyword": r"demänovsk", "wikidata": "https://www.wikidata.org/wiki/Q1186358", "coords": [49.002, 19.584], "desc": "Najdlhší jaskynný systém na Slovensku."},
    {"name": "Čachtická jaskyňa", "keyword": r"čachtic", "wikidata": "https://www.wikidata.org/wiki/Q3506161", "coords": [48.723, 17.789], "desc": "Zložitý labyrint v Čachtickom krase."},
    {"name": "Jasovská jaskyňa", "keyword": r"jasov", "wikidata": "https://www.wikidata.org/wiki/Q577749", "coords": [48.678, 20.976], "desc": "Významná archeologická a biospeleologická lokalita."},
    {"name": "Gombasecká jaskyňa", "keyword": r"gombas", "wikidata": "https://www.wikidata.org/wiki/Q599292", "coords": [48.563, 20.468], "desc": "Svetoznáma unikátnou ihlicovitou brčkovou výzdobou."},
    {"name": "Domica", "keyword": r"domic", "wikidata": "https://www.wikidata.org/wiki/Q908865", "coords": [48.478, 20.472], "desc": "Pýcha Slovenského krasu, prepojená s jaskyňou Baradla v Maďarsku."},
    {"name": "Dobšinská ľadová jaskyňa", "keyword": r"dobšin", "wikidata": "https://www.wikidata.org/wiki/Q833789", "coords": [48.868, 20.303], "desc": "Unikátna ľadová jaskyňa zapísaná v UNESCO."},
    {"name": "Ochtinská aragonitová jaskyňa", "keyword": r"ochtin", "wikidata": "https://www.wikidata.org/wiki/Q1058092", "coords": [48.664, 20.309], "desc": "Vzácna aragonitová jaskyňa s excentrickými formami výzdoby."},
    {"name": "Jaskyňa Driny", "keyword": r"drin", "wikidata": "https://www.wikidata.org/wiki/Q1259174", "coords": [48.502, 17.412], "desc": "Jediná sprístupnená jaskyňa na západnom Slovensku (Malé Karpaty)."},
    {"name": "Belianska jaskyňa", "keyword": r"belians", "wikidata": "https://www.wikidata.org/wiki/Q815598", "coords": [49.228, 20.316], "desc": "Jediná sprístupnená jaskyňa vo Vysokých/Belianskych Tatrách."},
    {"name": "Harmanecká jaskyňa", "keyword": r"harmanec", "wikidata": "https://www.wikidata.org/wiki/Q1585671", "coords": [48.814, 19.039], "desc": "Biela jaskyňa s bohatým výskytom mäkkého sintra."},
    {"name": "Bystrianska jaskyňa", "keyword": r"bystrian", "wikidata": "https://www.wikidata.org/wiki/Q1018706", "coords": [48.841, 19.596], "desc": "Najvýznamnejšia jaskyňa Horehronského podolia."},
    {"name": "Silická ľadnica", "keyword": r"silic", "wikidata": "https://www.wikidata.org/wiki/Q3504104", "coords": [48.557, 20.503], "desc": "Najnižšie položená ľadová priepasť mierneho pásma."},
    {"name": "Stratenská jaskyňa", "keyword": r"straten", "wikidata": "https://www.wikidata.org/wiki/Q12053724", "coords": [48.887, 20.345], "desc": "Druhý najdlhší jaskynný systém na Slovensku."},
    {"name": "Jaskyňa Javorinka", "keyword": r"javorin", "wikidata": "https://www.wikidata.org/wiki/Q12022416", "coords": [49.256, 20.122], "desc": "Hlboká vysokohorská jaskyňa v Javorovej doline (Tatry)."},
    {"name": "Skalistý potok", "keyword": r"skalist", "wikidata": "https://www.wikidata.org/wiki/Q12054695", "coords": [48.618, 20.871], "desc": "Najhlbší jaskynný systém v Slovenskom krase."},
    {"name": "Krásnohorská jaskyňa", "keyword": r"krásnohor", "wikidata": "https://www.wikidata.org/wiki/Q12031776", "coords": [48.591, 20.598], "desc": "Krásnohorská jaskyňa so slávnym obrovským kvapľom."},
    {"name": "Jaskyňa Mŕtvych netopierov", "keyword": r"mŕtvych netopier", "wikidata": "https://www.wikidata.org/wiki/Q12022413", "coords": [48.925, 19.645], "desc": "Jediná vysokohorská sprístupnená jaskyňa."},
    {"name": "Liskovská jaskyňa", "keyword": r"liskov", "wikidata": "https://www.wikidata.org/wiki/Q12033682", "coords": [49.088, 19.349], "desc": "Významná jaskyňa v Liptovskej kotline."},
    {"name": "Plavecká jaskyňa", "keyword": r"plaveck", "wikidata": "https://www.wikidata.org/wiki/Q12045610", "coords": [48.484, 17.268], "desc": "Významná jaskyňa v Malých Karpatoch."},
    {"name": "Jaskyňa Štefanová", "keyword": r"štefanov", "wikidata": "https://www.wikidata.org/wiki/Q12057398", "coords": [49.006, 19.593], "desc": "Jaskyňa v Demänovskej doline."},
    {"name": "Mesačný tieň", "keyword": r"mesačný tieň", "wikidata": "https://www.wikidata.org/wiki/Q12036577", "coords": [48.948, 20.158], "desc": "Vysokohorský jaskynný systém v Belianskych Tatrách."},
    {"name": "Javorová priepasť", "keyword": r"javorov", "wikidata": "https://www.wikidata.org/wiki/Q12022394", "coords": [49.232, 20.141], "desc": "Vysokohorská priepasť v Tatrách."},
    {"name": "Priepasť Brázda", "keyword": r"brázda", "wikidata": "https://www.wikidata.org/wiki/Q12047376", "coords": [48.562, 20.485], "desc": "Známa hlboká priepasť na Silickej planine."},
    {"name": "Kunia priepasť", "keyword": r"kuni", "wikidata": "https://www.wikidata.org/wiki/Q12031980", "coords": [48.653, 20.898], "desc": "Hlboká priepasť na Jasovskej planine."},
    {"name": "Diviačia priepasť", "keyword": r"diviač", "wikidata": "https://www.wikidata.org/wiki/Q12015250", "coords": [48.598, 20.701], "desc": "Hlboká priepasť na Plešiveckej planine."},
    {"name": "Obrovská priepasť", "keyword": r"obrovsk", "wikidata": "https://www.wikidata.org/wiki/Q12041926", "coords": [48.558, 20.612], "desc": "Známa priepasť na Dolnom vrchu."},
    {"name": "Zvonivá priepasť", "keyword": r"zvoniv", "wikidata": "https://www.wikidata.org/wiki/Q12068994", "coords": [48.599, 20.579], "desc": "Priepasť s krásnou kvapľovou výzdobou."},
    {"name": "Snežná jaskyňa", "keyword": r"snežn", "wikidata": "https://www.wikidata.org/wiki/Q12054942", "coords": [48.814, 20.252], "desc": "Ľadová/snežná priepasť v Spišsko-gemerskom krase."}
]

# Taxonomy / Themes keywords
TAXONOMY_THEMES = [
    {"tag": "Biospeleológia 🦇", "keywords": [r"netopier", r"chiropter", r"myotis", r"rhinolophus", r"pipistrellus", r"faun", r"živoč", r"chrobák", r"organizm", r"biológ", r"troglobiont", r"chvostoskok"]},
    {"tag": "Kartografia a meranie 🗺️", "keywords": [r"meran", r"mapovan", r"kartograf", r"polohopis", r"zameran", r"plán", r"profil", r"meral", r"technika mer", r"teodolit", r"disto"]},
    {"tag": "Mineralógia a geológia 💎", "keywords": [r"mineral", r"sinter", r"výzdoba", r"kalcit", r"aragonit", r"geológ", r"tektonika", r"sediment", r"krasovaten", r"kryštál"]},
    {"tag": "Bezpečnosť a záchrana ⛑️", "keywords": [r"nehoda", r"záchrana", r"smrť", r"úrazy", r"tragéd", r"pátranie", r"bezpečnos", r"smernica", r"cvičenie záchr", r"lekár", r"speleomedicina"]},
    {"tag": "Speleopotápanie 🤿", "keywords": [r"potápa", r"speleopotáp", r"sifón", r"zatopen", r"pod vodou", r"potápač", r"potápačský", r"vynore", r"depresia sifónu"]},
    {"tag": "Expedície a zahraničie 🌍", "keywords": [r"expedíc", r"zahranič", r"rumunsk", r"tureck", r"gréck", r"talians", r"kaukaz", r"mexik", "čína", r"rakúsk", r"čierna hora", r"slovinsko", r"albánsko", r"bulhars"]},
    {"tag": "História a osobnosti 📜", "keywords": [r"histór", r"výroč", r"jubile", r"lalkovič", r"bella", r"sabol", r"jakál", r"droppa", r"archeol", r"kronika", r"spomienka", r"nekrológ", r"múzeum", r"archív"]},
    {"tag": "Speleoturistika a ochrana 🌲", "keywords": [r"ochrana", r"chránen", r"čistenie", r"odpad", r"sprístupn", r"národný park", r"verejnos", r"speleoturist", r"exkurz", r"turis"]}
]

# SSS Speleological Groups (SSS Groups)
SSS_GROUPS = [
    {"name": "OS Liptovský Mikuláš", "keywords": [r"os liptovsk", r"liptovský mikuláš", r"skupina liptovsk", r"demänovskájaskyňa", r"demänovskí jaskyniari"]},
    {"name": "Speleoklub Šariš", "keywords": [r"speleoklub šariš", r"šariš", r"prešov", r"drienovsk", r"zlá diera"]},
    {"name": "OS Ružomberok", "keywords": [r"os ružomberok", r"ružomberok", r"liskovská", r"choč", r"kúpele lúčky"]},
    {"name": "Speleoklub Rožňava", "keywords": [r"rožňava", r"speleoklub rožňava", r"slovenský kras", r"silica", r"plešivec", r"koniar"]},
    {"name": "Speleoklub Banská Bystrica", "keywords": [r"banská bystrica", r"banskobystr", r"harmanec", r"sása", r"sklené teplice"]},
    {"name": "Speleoklub Košice", "keywords": [r"speleoklub košice", r"košice", r"košick", r"jasov", r"zádiel", r"medzev"]},
    {"name": "Speleoklub Nicolaus", "keywords": [r"speleoklub nicolaus", r"nicolaus", r"svätý mikuláš", r"ohište", r"kr Krakov"]},
    {"name": "Speleoklub Plavecké Podhradie", "keywords": [r"plavecké podhradie", r"plaveck", r"plavecká", r"červené kopce", r"malé karpaty"]},
    {"name": "Speleoklub Slovenský raj", "keywords": [r"slovenský raj", r"tornaľa", r"spišk", r"stratensk", r"dobšin"]},
    {"name": "OS Čachtice", "keywords": [r"os čachtice", r"čachtic", r"čachtická", r"nové mesto"]},
    {"name": "OS Tisovec", "keywords": [r"os tisovec", r"tisovec", r"tisovsk", r"muránska planina", r"suché doly"]},
    {"name": "Speleoklub Zvolen", "keywords": [r"speleoklub zvolen", r"zvolen", r"zvolensk", r"pliešovce"]},
    {"name": "OS Žilina", "keywords": [r"os žilina", r"žilinsk", r"malá fatra", r"strážovské vrchy", r"mojžišova"]},
    {"name": "OS Martin", "keywords": [r"os martin", r"martinsk", r"veľká fatra", r"turiec", r"jasenská dolina"]},
    {"name": "OS Brezno", "keywords": [r"os brezno", r"brezno", r"horehron", r"bystriansk", r"ďumbiersk"]}
]

def enrich_article(art):
    """Enriches a single article object based on title and abstract text."""
    title = art.get("title", "")
    abstract = art.get("abstract", "")
    combined_text = (title + " " + (abstract if abstract else "")).lower()

    # 1. Match Caves
    matched_caves = []
    matched_wikidata = []
    for cave in MAJOR_CAVES:
        if article_mentions_cave({"title": title, "abstract": abstract}, cave["name"]):
            matched_caves.append(cave["name"])
            matched_wikidata.append({
                "name": cave["name"],
                "url": cave["wikidata"]
            })

    # 2. Match Taxonomy & Themes
    matched_tags = []
    for theme in TAXONOMY_THEMES:
        match_found = False
        for kw in theme["keywords"]:
            if re.search(kw, combined_text):
                match_found = True
                break
        if match_found:
            matched_tags.append(theme["tag"])

    if not matched_tags:
        matched_tags.append("Speleológia")

    # 3. Match SSS Groups
    matched_groups = []
    for group in SSS_GROUPS:
        for kw in group["keywords"]:
            if re.search(kw, combined_text):
                matched_groups.append(group["name"])
                break

    # Enrich article fields
    art["caves"] = matched_caves
    art["tags"] = matched_tags
    art["groups"] = matched_groups
    art["wikidata"] = matched_wikidata
    
    return art

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, "data", "articles_with_urls.json")
    
    if not os.path.exists(db_path):
        print(f"Error: Local database not found at {db_path}")
        return

    print("Loading articles from database...")
    with open(db_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print(f"Enriching {len(articles)} articles with semantic tags, caves, groups, and wikidata...")
    enriched_articles = []
    for art in articles:
        enriched_articles.append(enrich_article(art))

    # Save to local database
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(enriched_articles, f, ensure_ascii=False, indent=2)
    print(f"Saved enriched database to {db_path}.")

    # Copy to Astro source tree
    astro_db_path = os.path.join(base_dir, "web", "src", "data", "articles.json")
    if os.path.exists(os.path.dirname(astro_db_path)):
        with open(astro_db_path, "w", encoding="utf-8") as f:
            json.dump(enriched_articles, f, ensure_ascii=False, indent=2)
        print(f"Copied enriched database to Astro data store: {astro_db_path}")

if __name__ == "__main__":
    main()
