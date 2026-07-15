from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from . import models, database

# Secret key configuration for JWT
SECRET_KEY = "supersecretkey_change_in_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 days expiry

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def verify_password(plain_password, hashed_password):
    if hashed_password == "EXTERNAL_SUPABASE_AUTH":
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    import os
    import requests
    import re
    
    supabase_key = os.getenv("SUPABASE_KEY", "").strip().strip('"').strip("'")
    db_url = os.getenv("DATABASE_URL", "")
    
    match = re.search(r"@db\.([^.]+)\.supabase\.co", db_url)
    project_id = match.group(1) if match else None
    supabase_url = f"https://{project_id}.supabase.co" if project_id else ""
    
    if not supabase_url or not supabase_key:
        # Local custom JWT authentication fallback
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise credentials_exception
            user = db.query(models.User).filter(models.User.username == username).first()
            if user is None:
                raise credentials_exception
            return user
        except JWTError:
            raise credentials_exception

    # Supabase Verification
    try:
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {token}"
        }
        res = requests.get(f"{supabase_url}/auth/v1/user", headers=headers)
        if res.status_code != 200:
            raise credentials_exception
            
        supabase_user = res.json()
        user_id = supabase_user.get("id")
        email = supabase_user.get("email")
        metadata = supabase_user.get("user_metadata", {})
        username = metadata.get("username", email.split("@")[0])
        
        # Ensure user exists locally
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            user = models.User(
                id=user_id,
                username=username,
                email=email,
                hashed_password="EXTERNAL_SUPABASE_AUTH"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
        return user
    except Exception:
        raise credentials_exception
