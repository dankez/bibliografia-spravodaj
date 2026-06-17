import json
import re
import os

def clean_author_list(authors):
    cleaned = []
    i = 0
    while i < len(authors):
        current = authors[i].strip()
        is_initial = re.match(r'^[A-ZÁÄČĎÉÍĽĹŇÓÔŔŠŤÚÝŽ]\.$', current) is not None
        is_suffix = current.lower() in ['a kol.', 'a spol.', 'coll.', 'eds.', 'ed.']
        if (is_initial or is_suffix) and cleaned:
            cleaned[-1] = f"{cleaned[-1]}, {current}"
        else:
            cleaned.append(current)
        i += 1
    return cleaned

def clean_file(filepath):
    if not os.path.exists(filepath):
        print(f"File {filepath} does not exist, skipping.")
        return
        
    print(f"Cleaning authors in {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    modified_count = 0
    for art in data:
        orig = art['authors']
        cleaned = clean_author_list(orig)
        if orig != cleaned:
            art['authors'] = cleaned
            modified_count += 1
            
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully cleaned {modified_count} articles in {filepath}.")

if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    clean_file(os.path.join(base_dir, 'data', 'articles.json'))
    clean_file(os.path.join(base_dir, 'data', 'articles_with_urls.json'))
