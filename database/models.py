from datetime import datetime

from pydantic import BaseModel, EmailStr
from bson import ObjectId
from passlib.context import CryptContext
from passlib.hash import bcrypt
from enum import Enum as PyEnum

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserLogin(BaseModel):
    email: EmailStr
    username: str
    password: str


class UserProfile(UserLogin):
    first_name: str
    last_name: str


    class Config:
        json_encoders = {
            ObjectId: str
        }

    def set_password(self, password: str):
        self.password = bcrypt.hash(password)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    access_token_expiration: datetime


class Presentations(BaseModel):
    title: str
    price: int


class Purchases(BaseModel):
    user_id: str
    presentation_id: str
    purchase_date: datetime


class TypeStatusChoices(str, PyEnum):
    standard = "standard"
    premium = "premium"


class StatusChoices(str, PyEnum):
    active = "active"
    inactive = "inactive"


class Subscription(BaseModel):
    user_id: str
    type: TypeStatusChoices
    start_date: datetime
    end_date: datetime
    status: StatusChoices