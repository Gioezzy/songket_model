from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc
import uuid
import os

from . import models, schemas, database, ai_model, auth

# Automatically create SQLite tables if they do not exist
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Songket Generator API")

# CORS middleware configuration for mobile client access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory for client image retrieval
# Example: http://127.0.0.1:8000/static/images/image.png
app.mount("/static", StaticFiles(directory="static"), name="static")

# Map string Category ID to integer index matching PyTorch ImageFolder alphabetized dataset classification
CATEGORY_MAP = {
    'cat-001': 0, # Apel
    'cat-002': 1, # Baragi
    'cat-003': 2, # Bungo Satangkai
    'cat-004': 3, # Itiak Pulang Patang
    'cat-005': 4, # Pucuak Rabuang
    'cat-006': 5, # Rangkiang
    'cat-007': 6, # Saik Galamai
    'cat-008': 7, # Taratai
    'cat-009': 8, # Tulip
}

@app.on_event("startup")
def startup_event():
    # Load model on application startup
    ai_model.load_model()

# Database session dependency
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- MOBILE APP API ENDPOINTS ---

from fastapi.security import OAuth2PasswordRequestForm

@app.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    supabase_key = os.getenv("SUPABASE_KEY", "").strip().strip('"').strip("'")
    db_url = os.getenv("DATABASE_URL", "")
    import re
    match = re.search(r"@db\.([^.]+)\.supabase\.co", db_url)
    project_id = match.group(1) if match else None
    supabase_url = f"https://{project_id}.supabase.co" if project_id else ""
    
    role_val = user.role or "user"
    
    if not supabase_url or not supabase_key:
        db_user = db.query(models.User).filter((models.User.username == user.username) | (models.User.email == user.email)).first()
        if db_user:
            raise HTTPException(status_code=400, detail="Username or email already registered")
        
        hashed_password = auth.get_password_hash(user.password)
        new_user = models.User(
            id=f"usr-{uuid.uuid4().hex[:8]}",
            username=user.username,
            email=user.email,
            hashed_password=hashed_password,
            role=role_val
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email,
            "role": new_user.role,
            "createdAt": new_user.created_at,
            "updatedAt": new_user.updated_at
        }
        
    try:
        import requests
        payload = {
            "email": user.email,
            "password": user.password,
            "data": {
                "username": user.username,
                "role": role_val
            }
        }
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json"
        }
        res = requests.post(f"{supabase_url}/auth/v1/signup", json=payload, headers=headers)
        if res.status_code not in [200, 201]:
            err_msg = res.json().get("msg", "Failed to register on Supabase Auth")
            raise HTTPException(status_code=res.status_code, detail=err_msg)
            
        sb_data = res.json()
        user_id = sb_data.get("id") or sb_data.get("user", {}).get("id")
        if not user_id:
            raise HTTPException(status_code=500, detail="Failed to retrieve user ID from Supabase signup response")
        
        new_user = models.User(
            id=user_id,
            username=user.username,
            email=user.email,
            hashed_password="EXTERNAL_SUPABASE_AUTH",
            role=role_val
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        return {
            "id": new_user.id,
            "username": new_user.username,
            "email": new_user.email,
            "role": new_user.role,
            "createdAt": new_user.created_at,
            "updatedAt": new_user.updated_at
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/login", response_model=schemas.Token)
def login(login_data: schemas.UserLogin, db: Session = Depends(database.get_db)):
    supabase_key = os.getenv("SUPABASE_KEY", "").strip().strip('"').strip("'")
    db_url = os.getenv("DATABASE_URL", "")
    import re
    match = re.search(r"@db\.([^.]+)\.supabase\.co", db_url)
    project_id = match.group(1) if match else None
    supabase_url = f"https://{project_id}.supabase.co" if project_id else ""
    
    if not supabase_url or not supabase_key:
        user = db.query(models.User).filter(models.User.username == login_data.username).first()
        if not user or not auth.verify_password(login_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token = auth.create_access_token(data={"sub": user.username, "role": user.role})
        return {"access_token": access_token, "token_type": "bearer"}
        
    email = login_data.username
    if "@" not in email:
        user = db.query(models.User).filter(models.User.username == login_data.username).first()
        if user:
            email = user.email
            
    try:
        import requests
        payload = {
            "email": email,
            "password": login_data.password
        }
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json"
        }
        res = requests.post(f"{supabase_url}/auth/v1/token?grant_type=password", json=payload, headers=headers)
        if res.status_code != 200:
            err_msg = res.json().get("error_description", "Incorrect username or password")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err_msg)
            
        sb_data = res.json()
        access_token = sb_data.get("access_token")
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/users/me/password")
def update_password(
    payload: schemas.PasswordUpdate, 
    current_user: models.User = Depends(auth.get_current_user), 
    token: str = Depends(auth.oauth2_scheme),
    db: Session = Depends(database.get_db)
):
    supabase_key = os.getenv("SUPABASE_KEY", "").strip().strip('"').strip("'")
    db_url = os.getenv("DATABASE_URL", "")
    import re
    match = re.search(r"@db\.([^.]+)\.supabase\.co", db_url)
    project_id = match.group(1) if match else None
    supabase_url = f"https://{project_id}.supabase.co" if project_id else ""

    if not supabase_url or not supabase_key:
        if not auth.verify_password(payload.old_password, current_user.hashed_password):
            raise HTTPException(status_code=400, detail="Current password does not match")
        current_user.hashed_password = auth.get_password_hash(payload.new_password)
        db.commit()
        return {"data": {"success": True}}

    try:
        import requests
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        res = requests.put(f"{supabase_url}/auth/v1/user", json={"password": payload.new_password}, headers=headers)
        if res.status_code != 200:
            err_msg = res.json().get("msg", "Failed to update password on Supabase")
            raise HTTPException(status_code=res.status_code, detail=err_msg)
        return {"data": {"success": True}}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def get_clean_base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", "http")
    base_url = str(request.base_url).rstrip("/")
    if proto == "https" or any(domain in base_url for domain in ["pinggy.link", "ngrok-free.app", "localtunnel.me", "loca.lt", "hf.space"]):
        if base_url.startswith("http://"):
            base_url = base_url.replace("http://", "https://")
    return base_url


@app.get("/categories")
def get_categories(request: Request, db: Session = Depends(database.get_db)):
    categories = db.query(models.Category).all()
    base_url = get_clean_base_url(request)

    
    # Format categories response matching Flutter ApiMotifRepository expectation
    result = []
    for cat in categories:
        preview_url = ""
        if cat.preview_image:
            if cat.preview_image.startswith("http"):
                preview_url = cat.preview_image
            else:
                preview_url = f"{base_url}/static/images/{cat.preview_image}"
        result.append({
            "id": cat.id,
            "name": cat.name,
            "description": cat.description,
            "preview_image": preview_url,
            "created_at": cat.created_at.isoformat() if cat.created_at else "2026-06-01T00:00:00",
            "updated_at": cat.updated_at.isoformat() if cat.updated_at else (cat.created_at.isoformat() if cat.created_at else "2026-06-01T00:00:00")
        })
    return {"data": result}

@app.post("/generate")
def generate_motif(req: schemas.GenerateRequest, request: Request, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    # 1. Get generator index mapping from category_id
    cat_idx = CATEGORY_MAP.get(req.category_id, 0)
    
    # 2. Invoke PyTorch generator model
    try:
        filename, used_seed = ai_model.generate_songket(category_idx=cat_idx, seed=req.noise_seed)
    except Exception as e:
        print(f"Error during generate_songket: {e}")
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500, 
            content={"error": {"code": "GENERATION_FAILED", "message": str(e)}}
        )
    
    # 3. Upload to Supabase Storage if configured; otherwise fallback to local static file serving
    import os
    from .supabase_storage import upload_generated_motif
    
    filepath = os.path.join(ai_model.OUTPUT_DIR, filename)
    public_url = upload_generated_motif(filename, filepath)
    
    if public_url:
        image_url = public_url
        try:
            os.remove(filepath)
        except Exception as e:
            print(f"Failed to remove local file: {e}")
    else:
        base_url = get_clean_base_url(request)
        image_url = f"{base_url}/static/images/{filename}"

    
    # 4. Generate unique ID for motif history entry
    result_id = f"gen-{uuid.uuid4().hex[:8]}"
    motif_id = result_id
    
    # Save generation entry to SQLite history table
    category = db.query(models.Category).filter(models.Category.id == req.category_id).first()
    cat_name = category.name if category else "Unknown"
    
    try:
        new_history = models.History(
            id=result_id,
            category_id=req.category_id,
            category_name=cat_name,
            generated_image=image_url,
            noise_seed=used_seed,
            user_id=current_user.id
        )
        db.add(new_history)
        db.commit()
        db.refresh(new_history)
        
        # 5. Format response to match Flutter GenerateResult expectations
        # Ensure ISO8601 timezone-aware format
        created_at_str = new_history.created_at.isoformat()
        
        print(f"Generation successful: motif_id={motif_id}, seed={used_seed}")
        
        return {
            "data": {
                "motif": {
                    "id": motif_id,
                    "history_id": result_id,
                    "category_id": req.category_id,
                    "image_url": image_url,
                    "created_at": created_at_str,
                    "title": f"Songket {cat_name}"
                },
                "used_seed": used_seed,
                "history_id": result_id
            }
        }
    except Exception as e:
        db.rollback()
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"error": {"code": "DATABASE_ERROR", "message": str(e)}})

def ensure_https_url(url: str) -> str:
    if url and url.startswith("http://") and any(domain in url for domain in ["pinggy.link", "ngrok-free.app", "localtunnel.me", "loca.lt", "hf.space"]):
        return url.replace("http://", "https://")
    return url


from typing import Optional

@app.get("/histories")
def get_histories(
    page: Optional[int] = 1,
    page_size: Optional[int] = 20,
    sort: Optional[str] = "created_at_desc",
    category_id: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db)
):
    query = db.query(models.History).filter(models.History.user_id == current_user.id)
    
    if category_id:
        query = query.filter(models.History.category_id == category_id)
        
    if sort == "created_at_asc":
        query = query.order_by(models.History.created_at.asc())
    else:
        query = query.order_by(models.History.created_at.desc())
        
    # Offset and limit pagination
    if page and page_size:
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        
    histories = query.all()
    
    result = []
    for hist in histories:
        result.append({
            "id": hist.id,
            "category_id": hist.category_id,
            "category_name": hist.category_name,
            "generated_image": ensure_https_url(hist.generated_image),
            "created_at": hist.created_at.isoformat() if hist.created_at else "2026-06-01T00:00:00"
        })
        
    return {"data": result}


@app.get("/motifs/{motif_id}/download")
def download_motif(motif_id: str, request: Request, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    history = db.query(models.History).filter(
        models.History.id == motif_id,
        models.History.user_id == current_user.id
    ).first()
    if not history:
        raise HTTPException(status_code=404, detail="Motif not found")
        
    filename = history.generated_image.split("/")[-1]
    return {
        "data": {
            "url": ensure_https_url(history.generated_image),
            "file_name": filename
        }
    }

@app.post("/motifs/{motif_id}/save")
def save_motif(motif_id: str, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    history = db.query(models.History).filter(
        models.History.id == motif_id,
        models.History.user_id == current_user.id
    ).first()
    if not history:
        raise HTTPException(status_code=404, detail="Motif not found")
        
    return {
        "data": {
            "id": history.id,
            "category_id": history.category_id,
            "category_name": history.category_name,
            "generated_image": ensure_https_url(history.generated_image),
            "created_at": history.created_at.isoformat() if history.created_at else "2026-06-01T00:00:00"
        }
    }

@app.get("/motifs/{motif_id}")
def get_motif(motif_id: str, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    # Find motif in database by motif_id
    history = db.query(models.History).filter(
        models.History.id == motif_id,
        models.History.user_id == current_user.id
    ).first()
    if not history:
        raise HTTPException(status_code=404, detail="Motif not found")
        
    return {
        "data": {
            "id": motif_id,
            "history_id": history.id,
            "category_id": history.category_id,
            "image_url": ensure_https_url(history.generated_image),
            "created_at": history.created_at.isoformat() if history.created_at else "2026-06-01T00:00:00",
            "title": f"Songket {history.category_name}"
        }
    }


@app.delete("/histories/{motif_id}")
def delete_motif(motif_id: str, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    history = db.query(models.History).filter(
        models.History.id == motif_id,
        models.History.user_id == current_user.id
    ).first()
    if not history:
        raise HTTPException(status_code=404, detail="Motif not found")
        
    db.delete(history)
    db.commit()
    return {"data": {"success": True}}


# --- ADMIN & ROLE-BASED ENDPOINTS ---

def get_current_admin(current_user: models.User = Depends(auth.get_current_user)) -> models.User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Admin role required"
        )
    return current_user

@app.get("/users/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "createdAt": current_user.created_at,
        "updatedAt": current_user.updated_at
    }

from typing import List

@app.get("/admin/users", response_model=List[schemas.UserResponse])
def get_all_users(
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(database.get_db)
):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "createdAt": u.created_at,
            "updatedAt": u.updated_at
        } for u in users
    ]

@app.delete("/admin/users/{user_id}")
def delete_user(
    user_id: str,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(database.get_db)
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    db.delete(user)
    db.commit()
    return {"success": True}

@app.get("/admin/histories")
def get_all_histories(
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(database.get_db)
):
    histories = db.query(models.History).order_by(models.History.created_at.desc()).all()
    return {
        "data": [
            {
                "id": h.id,
                "category_id": h.category_id,
                "category_name": h.category_name,
                "generated_image": ensure_https_url(h.generated_image),
                "noise_seed": h.noise_seed,
                "user_id": h.user_id,
                "created_at": h.created_at.isoformat() if h.created_at else "2026-06-01T00:00:00"
            } for h in histories
        ]
    }

@app.post("/admin/categories", response_model=schemas.CategoryResponse)
def create_category(
    category: schemas.CategoryCreate,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(database.get_db)
):
    cat_id = category.name.lower().replace(" ", "-")
    db_cat = db.query(models.Category).filter(models.Category.id == cat_id).first()
    if db_cat:
        raise HTTPException(status_code=400, detail="Category already exists")
    
    new_cat = models.Category(
        id=cat_id,
        name=category.name,
        description=category.description,
        preview_image=category.preview_image
    )
    db.add(new_cat)
    db.commit()
    db.refresh(new_cat)
    return {
        "id": new_cat.id,
        "name": new_cat.name,
        "description": new_cat.description,
        "previewImage": ensure_https_url(new_cat.preview_image),
        "createdAt": new_cat.created_at,
        "updatedAt": new_cat.updated_at or new_cat.created_at
    }

