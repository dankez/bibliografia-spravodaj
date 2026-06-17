#!/usr/bin/env python3
"""
Zotero Uploader for SSS Bibliography
Pushes speleological bibliography metadata to Zotero API.
Uses pure requests library for portability.
"""

import os
import json
import sys
import time
import uuid
import argparse
import requests

# Zotero API Base URL
BASE_URL = "https://api.zotero.org"

def parse_creator(author_str):
    """
    Parses author string into Zotero creator object.
    Supports 'LastName, FirstName' or single name 'Anonymus'.
    """
    author_str = author_str.strip()
    if ',' in author_str:
        parts = author_str.split(',', 1)
        last_name = parts[0].strip()
        first_name = parts[1].strip()
        return {
            "creatorType": "author",
            "firstName": first_name,
            "lastName": last_name
        }
    else:
        # Single-field name for institutions, anonyms, etc.
        return {
            "creatorType": "author",
            "name": author_str
        }

def get_headers(api_key):
    """Returns headers required for Zotero API."""
    return {
        "Zotero-API-Key": api_key,
        "Content-Type": "application/json"
    }

def get_library_prefix(library_id, library_type):
    """Returns the URL prefix for user or group library."""
    if library_type.lower() == 'user':
        return f"{BASE_URL}/users/{library_id}"
    else:
        return f"{BASE_URL}/groups/{library_id}"

def get_existing_article_ids(library_id, library_type, api_key):
    """
    Fetches all items from Zotero and extracts our custom ID from the 'extra' field.
    This enables duplicate prevention and resuming interrupted runs.
    """
    print("Fetching existing items from Zotero to check for duplicates...")
    existing_ids = set()
    prefix = get_library_prefix(library_id, library_type)
    url = f"{prefix}/items"
    
    headers = get_headers(api_key)
    params = {
        "limit": 100,
        "start": 0,
        "itemType": "journalArticle"
    }
    
    while True:
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 403:
                print("Error 403: Forbidden. Verify your Zotero API Key and Library ID permissions.")
                sys.exit(1)
            elif response.status_code != 200:
                print(f"Error fetching items: {response.status_code} - {response.text}")
                break
                
            items = response.json()
            if not items:
                break
                
            for item in items:
                extra = item.get("data", {}).get("extra", "")
                # Extract 'ID: <number>' from the extra field
                for line in extra.split('\n'):
                    if line.startswith("SSS_ID:"):
                        try:
                            art_id = int(line.split(":", 1)[1].strip())
                            existing_ids.add(art_id)
                        except ValueError:
                            pass
            
            print(f"  Loaded {len(items)} items (Total found: {len(existing_ids)} unique SSS IDs)...")
            
            # Check if there's a next page
            if "next" in response.links:
                params["start"] += 100
            else:
                break
                
        except Exception as e:
            print(f"Error querying Zotero API: {e}")
            break
            
    print(f"Finished check. Found {len(existing_ids)} articles already in Zotero.")
    return existing_ids

def upload_batch(library_id, library_type, api_key, items_batch):
    """Uploads a batch of up to 50 items to Zotero."""
    prefix = get_library_prefix(library_id, library_type)
    url = f"{prefix}/items"
    headers = get_headers(api_key)
    
    # Zotero-Write-Token prevents duplicate processing on network retries (max 32 chars)
    headers["Zotero-Write-Token"] = uuid.uuid4().hex
    
    response = requests.post(url, headers=headers, json=items_batch)
    if response.status_code == 200 or response.status_code == 201:
        result = response.json()
        success_keys = list(result.get("success", {}).values())
        failed = result.get("failed", {})
        if failed:
            print(f"  Warning: {len(failed)} items failed to upload in this batch:")
            for idx, fail_info in failed.items():
                print(f"    Index {idx}: {fail_info.get('message')}")
        return len(success_keys)
    else:
        print(f"  Failed to upload batch. Status code: {response.status_code}")
        print(f"  Response: {response.text}")
        return 0

def build_zotero_item(art):
    """Converts a parsed article dictionary to a Zotero journalArticle schema."""
    creators = [parse_creator(author) for author in art.get("authors", [])]
    
    # Abstract clean-up
    abstract = art.get("abstract", "")
    
    # Extra field - stores metadata for our CMS and search engine
    # SSS_ID is crucial for duplicate prevention
    extra_lines = [
        f"SSS_ID: {art['id']}",
        f"Volume: {art.get('volume', '')}",
        f"Issue: {art.get('issue', '')}",
        f"Pages: {art.get('pages', '')}"
    ]
    if art.get("extras"):
        extra_lines.append(f"Extras: {', '.join(art['extras'])}")
        
    extra_str = "\n".join(extra_lines)
    
    # Create tags
    tags = [
        {"tag": "Spravodaj SSS"},
        {"tag": f"rok_{art['year']}"}
    ]
    # Add volume/issue tags if present
    if art.get("volume"):
        tags.append({"tag": f"rocnik_{art['volume']}"})
    if art.get("issue"):
        tags.append({"tag": f"cislo_{art['issue']}"})
        
    # Map to Zotero Journal Article Schema
    item = {
        "itemType": "journalArticle",
        "title": art["title"],
        "creators": creators,
        "publicationTitle": "Spravodaj Slovenskej speleologickej spoločnosti",
        "volume": art.get("volume", ""),
        "issue": art.get("issue", ""),
        "pages": art.get("pages", ""),
        "date": str(art["year"]),
        "abstractNote": abstract,
        "url": art.get("pdf_url", "") or "",
        "extra": extra_str,
        "tags": tags
    }
    
    return item

def main():
    parser = argparse.ArgumentParser(description="Upload Slovak Speleological Society bibliography to Zotero")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of articles to upload (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Print items without uploading them")
    parser.add_argument("--skip-check", action="store_true", help="Skip checking Zotero for existing items")
    args = parser.parse_args()

    # Load credentials from environment
    api_key = os.environ.get("ZOTERO_API_KEY")
    library_id = os.environ.get("ZOTERO_LIBRARY_ID")
    library_type = os.environ.get("ZOTERO_LIBRARY_TYPE", "group") # default to group
    
    if not args.dry_run:
        if not api_key or not library_id:
            print("Error: ZOTERO_API_KEY and ZOTERO_LIBRARY_ID environment variables are required.")
            print("Please set them in your environment, e.g.:")
            print("  export ZOTERO_API_KEY=\"your_api_key\"")
            print("  export ZOTERO_LIBRARY_ID=\"your_group_or_user_id\"")
            print("  export ZOTERO_LIBRARY_TYPE=\"group\" # or \"user\"")
            print("\nRunning in DRY-RUN mode instead...")
            args.dry_run = True
            
    # Load articles
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(base_dir, "data", "articles_with_urls.json")
    
    if not os.path.exists(data_path):
        print(f"Error: Articles JSON not found at {data_path}")
        sys.exit(1)
        
    with open(data_path, "r", encoding="utf-8") as f:
        articles = json.load(f)
        
    print(f"Loaded {len(articles)} articles from local database.")
    
    # Check for existing items in Zotero
    existing_ids = set()
    if not args.dry_run and not args.skip_check:
        existing_ids = get_existing_article_ids(library_id, library_type, api_key)
        
    # Filter out already uploaded articles
    articles_to_upload = [a for a in articles if a["id"] not in existing_ids]
    print(f"Articles remaining to upload: {len(articles_to_upload)}")
    
    if args.limit:
        articles_to_upload = articles_to_upload[:args.limit]
        print(f"Limiting upload to first {args.limit} items.")
        
    if not articles_to_upload:
        print("No new articles to upload. Exiting.")
        return
        
    # Convert and batch
    zotero_items = [build_zotero_item(a) for a in articles_to_upload]
    
    if args.dry_run:
        print("\n=== DRY RUN MODE: Showing first 2 items ===")
        for i, item in enumerate(zotero_items[:2]):
            print(json.dumps(item, ensure_ascii=False, indent=2))
        print(f"\nDry run complete. Would have uploaded {len(zotero_items)} items.")
        return

    # Upload in batches of 50 (Zotero API limit for writes)
    batch_size = 50
    total_uploaded = 0
    
    print(f"\nStarting upload of {len(zotero_items)} items to Zotero...")
    for i in range(0, len(zotero_items), batch_size):
        batch = zotero_items[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(zotero_items) + batch_size - 1) // batch_size
        
        print(f"Uploading batch {batch_num}/{total_batches} ({len(batch)} items)...")
        
        success_count = upload_batch(library_id, library_type, api_key, batch)
        total_uploaded += success_count
        print(f"  Successfully uploaded {success_count} items (Total: {total_uploaded})")
        
        # Respect rate limits and API load
        time.sleep(1.5)
        
    print(f"\nUpload finished. Total items successfully created: {total_uploaded}")

if __name__ == "__main__":
    main()
