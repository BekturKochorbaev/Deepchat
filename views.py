from bson import ObjectId
from auth import SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, ALGORITHM
from datetime import timedelta, datetime
from database.models import UserProfile
from config import db
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import JWTError, jwt
import requests


async def get_user_profile(user_id: str):
    user = await db.user_profiles.find_one({"_id": ObjectId(user_id)})
    if user:
        user.pop("password", None)
        return user
    else:
        raise HTTPException(status_code=404, detail="User not found")


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


async def check_document_exists(collection, document_id):
    document = await collection.find_one({"_id": ObjectId(document_id)})
    if not document:
        raise HTTPException(status_code=404, detail=f"Document with ID {document_id} not found")
    return document


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, expire


def create_refresh_token(data: dict):
    token, _ = create_access_token(data, expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    return token


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = await db.user_profiles.find_one({"username": username})
    if user is None:
        raise credentials_exception
    return user

#-----------------------


API_AI = "https://051e-92-62-70-2.ngrok-free.app/v1/chat/completions"
PEXELS_API_KEY = "8BgJ7ceLcIpWfBHk76gykWAN7Q1yQe7htIjcVpUP0wNmdXad3pi0ehai"

# Генерация данных для первого слайда
def generate_first_slide(keyword: str):
    ai_payload = {
        "model": "models/Qwen/Qwen2.5-3B-Instruct",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. Always respond in the following format:\n\nTitle: <title>\nBrief Description: <description>"},
            {"role": "user", "content": f"Generate a short title and a brief description about {keyword}."}
        ],
        "max_tokens": 2048,
        "stream": False
    }

    ai_response = requests.post(API_AI, json=ai_payload)
    if ai_response.status_code != 200:
        return None

    ai_output = ai_response.json().get('choices', [{}])[0].get('message', {}).get('content', '')

    if "Title:" in ai_output and "Brief Description:" in ai_output:
        title = ai_output.split("Title:")[1].split("Brief Description:")[0].strip()
        description = ai_output.split("Brief Description:")[1].strip()
    else:
        title = f"Тема: {keyword}"
        description = ai_output

    title = title.replace("**", "").strip()
    description = description.replace("**", "").strip()

    pexels_response = requests.get(
        f'https://api.pexels.com/v1/search?query={keyword}&per_page=1&page=1',
        headers={'Authorization': PEXELS_API_KEY}
    )
    if pexels_response.status_code != 200:
        return None

    pexels_data = pexels_response.json()
    if not pexels_data.get('photos'):
        return None

    image_url = pexels_data['photos'][0]['src']['large']

    return {
        "keyword": keyword,
        "title": title,
        "description": description,
        "image_url": image_url,
        "created_at": datetime.now()
    }

# Генерация данных для второго слайда
def generate_second_slide(keyword: str):
    ai_payload = {
        "model": "models/Qwen/Qwen2.5-3B-Instruct",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. Always respond in the following format:\n\nTitle: <title>\nSubtitle 1: <subtitle 1>\nDescription 1: <description 1>\nSubtitle 2: <subtitle 2>\nDescription 2: <description 2>\nSubtitle 3: <subtitle 3>\nDescription 3: <description 3>\nSubtitle 4: <subtitle 4>\nDescription 4: <description 4>"},
            {"role": "user", "content": f"Generate a title, four subtitles, and descriptions for each subtitle about {keyword}."}
        ],
        "max_tokens": 2048,
        "stream": False
    }

    ai_response = requests.post(API_AI, json=ai_payload)
    if ai_response.status_code != 200:
        return None

    ai_output = ai_response.json().get('choices', [{}])[0].get('message', {}).get('content', '')

    try:
        title = ai_output.split("Title:")[1].split("Subtitle 1:")[0].strip()
        subtitle_1 = ai_output.split("Subtitle 1:")[1].split("Description 1:")[0].strip()
        description_1 = ai_output.split("Description 1:")[1].split("Subtitle 2:")[0].strip()
        subtitle_2 = ai_output.split("Subtitle 2:")[1].split("Description 2:")[0].strip()
        description_2 = ai_output.split("Description 2:")[1].split("Subtitle 3:")[0].strip()
        subtitle_3 = ai_output.split("Subtitle 3:")[1].split("Description 3:")[0].strip()
        description_3 = ai_output.split("Description 3:")[1].split("Subtitle 4:")[0].strip()
        subtitle_4 = ai_output.split("Subtitle 4:")[1].split("Description 4:")[0].strip()
        description_4 = ai_output.split("Description 4:")[1].strip()
    except Exception as e:
        title = f"Культура и традиции {keyword}"
        subtitle_1 = "Музыка"
        description_1 = "Традиционная турецкая музыка, народные танцы и современные жанры."
        subtitle_2 = "Кухня"
        description_2 = "Кебабы, мезе, пахлава и другие вкусные блюда."
        subtitle_3 = "Искусство"
        description_3 = "Керамика, ковры, каллиграфия и другие виды искусства."
        subtitle_4 = "Обычаи"
        description_4 = "Гостеприимство, уважение к старшим и семейные ценности."

    pexels_response = requests.get(
        f'https://api.pexels.com/v1/search?query={keyword}&per_page=1&page=2',
        headers={'Authorization': PEXELS_API_KEY}
    )
    if pexels_response.status_code != 200:
        return None

    pexels_data = pexels_response.json()
    if not pexels_data.get('photos'):
        return None

    image_url = pexels_data['photos'][0]['src']['large']

    return {
        "title": title,
        "subtitle_1": subtitle_1,
        "description_1": description_1,
        "subtitle_2": subtitle_2,
        "description_2": description_2,
        "subtitle_3": subtitle_3,
        "description_3": description_3,
        "subtitle_4": subtitle_4,
        "description_4": description_4,
        "image_url": image_url,
        "created_at": datetime.now()
    }
