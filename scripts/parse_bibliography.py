import re
import json
import os

def parse_bibliography(txt_path, json_path):
    print(f"Parsing bibliography from {txt_path}...")
    
    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    articles = []
    current_year = 1970
    current_volume = "I."
    current_issue = "1"
    
    # Regular expressions for metadata
    year_pattern = re.compile(r'^\s*Ročník\s+(\d{4})(?:\s*\(([^)]+)\))?\s*$', re.IGNORECASE)
    issue_pattern = re.compile(r'^\s*Číslo\s+([\d\s–-]+|mimoriadne číslo|zvláštne vydanie|kongres)\s*$', re.IGNORECASE)
    
    # Pattern to check if a line starts an article (e.g. "17. ")
    # Must remove form-feed \x0c before testing
    start_pattern = re.compile(r'^(\d+)\.\s+(.+)$')
    
    # Pattern to check if a line ends with pages (e.g. ", s. 26 – 29")
    pages_pattern = re.compile(r',\s*s\.\s*([\d\s–-]+)\s*$', re.IGNORECASE)
    
    # Helper to check for junk lines
    def is_junk_line(line_str):
        s = line_str.strip()
        if not s:
            return True
        if s == "Bibliografia Spravodaja SSS":
            return True
        if s.isdigit(): # Page numbers
            return True
        if s.lower() in ("zoznam článkov", "zoznam článkov", "predslov", "anotácia"):
            return True
        if re.match(r'^Ročník\s+\d+$', s, re.IGNORECASE):
            return True
        return False

    header_accumulator = []
    abstract_accumulator = []
    current_art_id = None
    last_saved_id = 0
    accumulating_header = False
    
    def save_current_article():
        nonlocal current_art_id, header_accumulator, abstract_accumulator, last_saved_id
        if current_art_id is None:
            return
            
        header_str = " ".join(header_accumulator).strip()
        abstract_str = " ".join(abstract_accumulator).strip()
        
        # Parse the header_str (format: "Number. Author: Title, extras, s. Pages")
        # Remove the leading number
        m_num = re.match(r'^(\d+)\.\s+(.+)$', header_str, re.DOTALL)
        if not m_num:
            return # Should not happen
            
        art_id = int(m_num.group(1))
        content = m_num.group(2).strip()
        
        # Extract pages from the end of the content
        m_pages = pages_pattern.search(content)
        if m_pages:
            pages_str = m_pages.group(1).strip().replace(' – ', '-').replace(' ', '')
            header_no_pages = content[:m_pages.start()].strip()
        else:
            pages_str = ""
            header_no_pages = content
            
        # Parse authors and title from header_no_pages
        colon_idx = header_no_pages.find(':')
        if colon_idx != -1:
            authors_str = header_no_pages[:colon_idx].strip()
            title_and_extras = header_no_pages[colon_idx+1:].strip()
            # Split authors by comma if followed by capital letter/initial
            authors = [a.strip() for a in re.split(r',\s*(?=[A-Z])', authors_str)]
        else:
            # No colon! Handle special authors or missing colons
            known_authors = ["/La/", "/lt/", "Roda, Š.", "Bella, P.", "Holúbek, P.", "Holúbek, p.", "H. Z."]
            found_author = None
            for ka in known_authors:
                if header_no_pages.startswith(ka):
                    found_author = ka
                    break
                    
            if found_author:
                authors = [found_author]
                title_and_extras = header_no_pages[len(found_author):].strip()
                if title_and_extras.startswith('.'):
                    title_and_extras = title_and_extras[1:].strip()
            else:
                # No author, it's just title (like "Bezpečnostné smernice", "Inzercia")
                authors = ["Anonymus"]
                title_and_extras = header_no_pages
                
        # Parse extras from title (illustr., res., lit.)
        extras = []
        title = title_and_extras
        
        extra_suffix_pattern = re.compile(r',\s*(\d+\s*(?:obr\.|pl\.\s*j\.|tab\.|fot\.)|res\.|lit\.|tab\.|map\.)\s*$', re.IGNORECASE)
        while True:
            suffix_match = extra_suffix_pattern.search(title)
            if suffix_match:
                extras.append(suffix_match.group(1).strip())
                title = title[:suffix_match.start()].strip()
            else:
                break
        extras.reverse()
        
        articles.append({
            'id': art_id,
            'authors': authors,
            'title': title,
            'pages': pages_str,
            'extras': extras,
            'year': current_year,
            'volume': current_volume,
            'issue': current_issue,
            'abstract': abstract_str
        })
        
        last_saved_id = art_id
        
        # Reset accumulators
        header_accumulator = []
        abstract_accumulator = []
        current_art_id = None

    for line_idx, line in enumerate(lines):
        line_str = line.replace('\x0c', '').strip()
        if not line_str:
            continue
            
        # Check for year/volume
        year_match = year_pattern.match(line_str)
        if year_match:
            save_current_article()
            current_year = int(year_match.group(1))
            current_volume = year_match.group(2) or ""
            print(f"  Found Year: {current_year} (Volume: {current_volume})")
            continue
            
        # Check for issue
        issue_match = issue_pattern.match(line_str)
        if issue_match:
            save_current_article()
            current_issue = issue_match.group(1).strip().replace(' – ', '-')
            print(f"    Found Issue: {current_issue}")
            continue
            
        # Skip junk lines
        if is_junk_line(line):
            continue
            
        # Check if this line starts a new article (e.g. "17. ")
        start_match = start_pattern.match(line_str)
        is_new_article = False
        if start_match:
            potential_id = int(start_match.group(1))
            next_expected_id = current_art_id + 1 if current_art_id is not None else last_saved_id + 1
            if potential_id == next_expected_id:
                is_new_article = True
                save_current_article()
                current_art_id = potential_id
                header_accumulator.append(line_str)
                accumulating_header = True

                
                # Check if this line also contains pages (completed header on single line)
                if pages_pattern.search(line_str):
                    accumulating_header = False
                    
        if not is_new_article:
            if current_art_id is not None:
                if accumulating_header:
                    header_accumulator.append(line_str)
                    # Check if this line completes the header
                    if pages_pattern.search(line_str):
                        accumulating_header = False
                else:
                    abstract_accumulator.append(line_str)


    # Save the last article
    save_current_article()

    print(f"Total articles parsed: {len(articles)}")
    
    # Save to JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully saved to {json_path}")
    
    # Verification
    ids = set(x['id'] for x in articles)
    missing = sorted(set(range(1, 2536)) - ids)
    print(f"Missing IDs: {missing}")

if __name__ == '__main__':
    parse_bibliography("sss-bibliografia/data/raw_text.txt", "sss-bibliografia/data/articles.json")
