import argparse
import re
import json
from pathlib import Path

def build_and_merge_urls(md_path, json_path, output_json_path):
    print(f"Reading scraped markdown from {md_path}...")
    with open(md_path, 'r', encoding='utf-8') as f:
        text = f.read()
        
    # Find all markdown links to PDFs
    links = re.findall(r'\[([^\]]+)\]\((https://sss.sk/wp-content/uploads/[^)]+\.pdf)\)', text)
    print(f"Found {len(links)} raw PDF links in markdown.")
    
    # Normalize link text to build a key map (e.g. "1970_3-4" -> URL)
    url_map = {}
    
    def normalize_link_text(t):
        t = t.strip()
        if 'bibliografia' in t.lower() or 'b17' in t.lower():
            return None
        # Find year
        year_match = re.search(r'\b(19\d\d|20\d\d)\b', t)
        if not year_match:
            return None
        year = int(year_match.group(1))
        
        # Clean words
        clean = re.sub(r'\b(19\d\d|20\d\d|Spravodajca|Spravodaj|Jaskyniar|Bulletin|Slovak|Speleological|Society)\b', '', t, flags=re.IGNORECASE)
        # Clean delimiters
        clean = clean.replace('-', ' ').replace('_', ' ').replace('+', ' ').replace('/', ' ').strip()
        
        # Check digits
        digits = re.findall(r'\d+', clean)
        if len(digits) == 1:
            issue = digits[0]
        elif len(digits) == 2:
            issue = f"{digits[0]}-{digits[1]}"
        else:
            issue = "1"
            
        if 'kongres' in t.lower():
            issue = 'kongres'
        elif 'mimoriadne' in t.lower():
            issue = 'mimoriadne'
            
        return year, issue

    for title, url in links:
        key_info = normalize_link_text(title)
        if key_info:
            year, issue = key_info
            key = f"{year}_{issue}"
            url_map[key] = url
            
    print(f"Normalized into {len(url_map)} unique issue URL keys.")
    
    # Save the URL map for reference
    base_dir = Path(__file__).resolve().parents[1]
    url_map_path = base_dir / "data" / "urls_map.json"
    with open(url_map_path, 'w', encoding='utf-8') as f:
        json.dump(url_map, f, ensure_ascii=False, indent=2)
    print(f"Saved URL map to {url_map_path}")
    
    # Now load the parsed articles
    print(f"Loading articles from {json_path}...")
    with open(json_path, 'r', encoding='utf-8') as f:
        articles = json.load(f)
        
    mapped_count = 0
    unmapped_keys = set()
    
    for a in articles:
        year = a['year']
        issue = a['issue']
        # Map key
        key = f"{year}_{issue}"
        
        # Fallbacks for key matching
        if key in url_map:
            a['pdf_url'] = url_map[key]
            mapped_count += 1
        else:
            # Let's try some variations (e.g. issue '3-4' vs '3+4')
            found = False
            for map_key, map_url in url_map.items():
                mk_year, mk_issue = map_key.split('_')
                if int(mk_year) == year:
                    # Check if issue numbers match
                    # e.g., '3-4' matches '3' and '4'
                    a_digits = set(re.findall(r'\d+', issue))
                    mk_digits = set(re.findall(r'\d+', mk_issue))
                    if a_digits == mk_digits and a_digits:
                        a['pdf_url'] = map_url
                        mapped_count += 1
                        found = True
                        break
            if not found:
                a['pdf_url'] = ""
                unmapped_keys.add(key)
                
    print(f"Successfully mapped {mapped_count} out of {len(articles)} articles.")
    print(f"Unmapped keys ({len(unmapped_keys)}): {sorted(list(unmapped_keys))}")
    
    # Save updated articles
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"Saved merged articles with URLs to {output_json_path}")

if __name__ == '__main__':
    base_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build PDF URL map from a scraped markdown page.")
    parser.add_argument("markdown", help="Markdown file containing links to sss.sk PDF files.")
    parser.add_argument("--articles", default=str(base_dir / "data" / "articles.json"))
    parser.add_argument("--output", default=str(base_dir / "data" / "articles_with_urls.json"))
    args = parser.parse_args()
    build_and_merge_urls(args.markdown, args.articles, args.output)
