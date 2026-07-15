from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class GenerateRequest(BaseModel):
    category_id: str
    resolution: str
    conditions: List[str] = []
    noise_seed: Optional[int] = None

class CategoryResponse(BaseModel):
    id: str
    name: str
    description: str
    previewImage: str
    createdAt: datetime
    updatedAt: datetime
    
    class Config:
        from_attributes = True

class HistoryResponse(BaseModel):
    id: str
    categoryId: str
    categoryName: str
    generatedImage: str
    createdAt: datetime

    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: Optional[str] = "user"

class UserLogin(BaseModel):
    username: str
    password: str

class PasswordUpdate(BaseModel):
    old_password: str
    new_password: str

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: Optional[str] = "user"
    createdAt: datetime
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str

class CategoryCreate(BaseModel):
    name: str
    description: str
    preview_image: str

