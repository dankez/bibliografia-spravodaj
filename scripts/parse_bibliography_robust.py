import re
import json

def parse_robust(txt_path, json_path):
    print(f"Parsing bibliography robustly from {txt_path}...")
    
    with open(txt_path, 'r', encoding='utf-8') as f:
        text = f.read()
        
    # Replace newlines with spaces temporarily in certain contexts,
    # but let's keep the text structure. We'll split the file by page breaks or lines.
    # Actually, we can split the text by article numbers.
    # The pattern is a newline, followed by a number, followed by a dot and space.
    # e.g., "\n17. " or "\n1580. "
    # We use a regex split that captures the numbers.
    # Note: we need to handle page breaks (form feeds \x0c) and headers/footers.
    
    # Let's clean the text first by removing page headers/footers
    cleaned_lines = []
    current_year = 1970
    current_volume = "I."
    current_issue = "1"
    
    year_pattern = re.compile(r'^\s*Ročník\s+(\d{4})\s*\(?([IVXLCDM.]+)?\)?\s*$', re.IGNORECASE)
    issue_pattern = re.compile(r'^\s*Číslo\s+([\d\s–-]+|mimoriadne číslo|zvláštne vydanie|kongres)\s*$', re.IGNORECASE)
    
    raw_lines = text.split('\n')
    
    # We will reconstruct the text but tag the year/issue changes in the text
    # so we can detect them during segment parsing.
    tagged_text_parts = []
    
    for line in raw_lines:
        line_str = line.strip()
        if not line_str:
            continue
            
        # Check for year/volume
        year_match = year_pattern.match(line_str)
        if year_match:
            current_year = int(year_match.group(1))
            current_volume = year_match.group(2) or ""
            tagged_text_parts.append(f"\n[YEAR:{current_year}:{current_volume}]\n")
            continue
            
        # Check for issue
        issue_match = issue_pattern.match(line_str)
        if issue_match:
            issue_val = issue_match.group(1).strip().replace(' – ', '-')
            current_issue = issue_val
            tagged_text_parts.append(f"\n[ISSUE:{current_issue}]\n")
            continue
            
        # Skip junk lines
        if line_str == "Bibliografia Spravodaja SSS":
            continue
        if line_str.isdigit(): # Page numbers
            continue
        if line_str.lower() in ("zoznam článkov", "zoznam článkov", "predslov", "anotácia"):
            continue
        if re.match(r'^Ročník\s+\d+$', line_str, re.IGNORECASE):
            continue
            
        tagged_text_parts.append(line + "\n")
        
    tagged_text = "".join(tagged_text_parts)
    
    # Now, split the tagged text by article numbers: "\n1. ", "\n2. ", ...
    # We look for a newline followed by number and dot and space.
    segments = re.split(r'\n(?=\d+\.\s+)', tagged_text)
    
    articles = []
    
    # Keep track of active year/issue
    active_year = 1970
    active_volume = "I."
    active_issue = "1"
    
    for seg in segments:
        seg_str = seg.strip()
        if not seg_str:
            continue
            
        # If the segment contains year/issue tags before the article number,
        # update our active year/issue
        tag_matches = re.findall(r'\[(YEAR|ISSUE):([^\]]+)\]', seg_str)
        for tag_type, tag_val in tag_matches:
            if tag_type == 'YEAR':
                parts = tag_val.split(':')
                active_year = int(parts[0])
                active_volume = parts[1] if len(parts) > 1 else ""
            elif tag_type == 'ISSUE':
                active_issue = tag_val
                
        # Remove the tags from the segment string for parsing
        seg_clean = re.sub(r'\[(YEAR|ISSUE):[^\]]+\]', '', seg_str).strip()
        
        # Match article: starts with number, dot, space
        art_match = re.match(r'^(\d+)\.\s+(.+)$', seg_clean, re.DOTALL)
        if not art_match:
            # Not an article segment (could be the preface text at the very beginning)
            continue
            
        art_id = int(art_match.group(1))
        content = art_match.group(2).strip()
        
        # Parse the content
        # It contains: Header (Author: Title, Pages) and Abstract (on subsequent lines)
        # Let's split content into lines
        content_lines = [l.strip() for l in content.split('\n') if l.strip()]
        if not content_lines:
            continue
            
        # Reconstruct header and find where it ends.
        # The header ends with pages: ", s. X-Y" or ", s. X".
        # Sometimes the header spans 2 lines, so we search for the page pattern in the lines.
        pages_match = None
        header_line_count = 0
        pages_pattern = re.compile(r',\s*s\.\s*(\d+(?:\s*–\s*\d+)?)\s*$', re.IGNORECASE)
        
        for i, line in enumerate(content_lines):
            m = pages_pattern.search(line)
            if m:
                pages_match = m
                header_line_count = i + 1
                break
                
        if pages_match:
            # We found the pages!
            pages_str = pages_match.group(1).strip().replace(' – ', '-')
            # Header lines are content_lines[:header_line_count]
            # Abstract lines are content_lines[header_line_count:]
            header_str = " ".join(content_lines[:header_line_count]).strip()
            abstract = " ".join(content_lines[header_line_count:]).strip()
            
            # Remove pages from header_str
            header_str_no_pages = header_str[:pages_match.start() + len(header_str) - len(content_lines[header_line_count-1])].strip()
        else:
            # Fallback if no pages found (e.g. some errata or missing page info)
            pages_str = ""
            header_str_no_pages = content_lines[0]
            abstract = " ".join(content_lines[1:]).strip()
            
        # Parse authors and title from header_str_no_pages
        # Standard: "Author, A.: Title"
        # Let's check for colon first
        colon_idx = header_str_no_pages.find(':')
        if colon_idx != -1:
            authors_str = header_str_no_pages[:colon_idx].strip()
            title_and_extras = header_str_no_pages[colon_idx+1:].strip()
            authors = [a.strip() for a in re.split(r',\s*(?=[A-Z])', authors_str)]
        else:
            # No colon! Handle special authors or missing colons
            # Special authors list
            known_authors = ["/La/", "/lt/", "Roda, Š.", "Bella, P.", "Holúbek, p.", "H. Z.", "Holúbek, P."]
            found_author = None
            for ka in known_authors:
                if header_str_no_pages.startswith(ka):
                    found_author = ka
                    break
                    
            if found_author:
                authors = [found_author]
                title_and_extras = header_str_no_pages[len(found_author):].strip()
                # Clean up leading dots/spaces if any
                if title_and_extras.startswith('.'):
                    title_and_extras = title_and_extras[1:].strip()
            else:
                # No author, it's just title (like "Bezpečnostné smernice", "Inzercia")
                authors = ["Anonymus"]
                title_and_extras = header_str_no_pages
                
        # Parse extras from title
        extras = []
        title = title_and_extras
        
        # Common suffixes
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
            'year': active_year,
            'volume': active_volume,
            'issue': active_issue,
            'abstract': abstract
        })
        
    print(f"Robust Parser: Total articles parsed: {len(articles)}")
    
    # Save to JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
        
    # Verify missing IDs
    ids = set(x['id'] for x in articles)
    missing = sorted(set(range(1, 2536)) - ids)
    print(f"Missing IDs in robust parsing: {missing}")

if __name__ == '__main__':
    parse_robust("sss-bibliografia/data/raw_text.txt", "sss-bibliografia/data/articles.json")
