import sys
from ai_scrape_new_issues import extract_pdf_toc

url = "https://sss.sk/wp-content/uploads/2026/06/Spravodaj_1_2026_vnutro_NET_web.pdf"
toc = extract_pdf_toc(url)
if toc:
    print(f"Extracted {len(toc)} characters.")
    print("First 500 characters:")
    print(toc[:500])
else:
    print("Failed to extract TOC.")
