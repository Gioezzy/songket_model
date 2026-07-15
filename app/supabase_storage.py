import os
import re
import requests

BUCKET_NAME = "generated-motifs"

def upload_generated_motif(filename: str, filepath: str) -> str:
    """
    Uploads a generated motif to Supabase Storage and returns the public URL.
    If the upload fails, returns None.
    """
    supabase_key = os.getenv("SUPABASE_KEY", "").strip().strip('"').strip("'")
    db_url = os.getenv("DATABASE_URL", "")

    # Extract Project ID
    match = re.search(r"@db\.([^.]+)\.supabase\.co", db_url)
    project_id = match.group(1) if match else None
    supabase_url = f"https://{project_id}.supabase.co" if project_id else ""

    if not project_id or not supabase_key:
        print("Supabase config missing, fallback to local storage.")
        return None
        
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}"
    }
    
    # 1. Ensure bucket exists (or try to create it)
    try:
        bucket_url = f"{supabase_url}/storage/v1/bucket"
        requests.post(bucket_url, json={"id": BUCKET_NAME, "name": BUCKET_NAME, "public": True}, headers=headers)
    except Exception as e:
        print(f"Error checking/creating bucket: {e}")
        
    # 2. Upload the file
    upload_url = f"{supabase_url}/storage/v1/object/{BUCKET_NAME}/{filename}"
    upload_headers = {
        **headers,
        "Content-Type": "image/webp",
        "x-upsert": "true"
    }
    
    try:
        with open(filepath, "rb") as f:
            file_data = f.read()
        res = requests.post(upload_url, data=file_data, headers=upload_headers)
        if res.status_code in [200, 201]:
            public_url = f"{supabase_url}/storage/v1/object/public/{BUCKET_NAME}/{filename}"
            return public_url
        else:
            print(f"Failed to upload generated motif to Supabase (Status {res.status_code}): {res.text}")
    except Exception as e:
        print(f"Error uploading generated motif to Supabase: {e}")
        
    return None
