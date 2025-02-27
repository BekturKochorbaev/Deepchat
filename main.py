from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Body, Request

from auth import ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
from config import collections, db
from database.models import UserProfile, TokenResponse, Subscription, Purchases, Presentations, UserLogin, \
    RefreshTokenRequest, RefreshTokenResponse, SlideRequest
from bson import ObjectId
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import timedelta, datetime
from views import get_user_profile, verify_password, check_document_exists, create_access_token, create_refresh_token, \
    get_current_user, generate_second_slide, generate_first_slide
from typing import List
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from fastapi import WebSocket, WebSocketDisconnect
import httpx
import json


app = FastAPI(title="DeepChat")
router = APIRouter()

origins = [
    "http://localhost:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Разрешенные домены
    allow_credentials=True,
    allow_methods=["*"],  # Разрешенные HTTP-методы (GET, POST, PUT и т.д.)
    allow_headers=["*"],  # Разрешенные заголовки
)

@router.post("/register/", response_model=TokenResponse)
async def register(user: UserProfile):
    existing_user = await db.user_profiles.find_one({"username": user.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    user_dict = user.dict()
    user.set_password(user_dict["password"])
    user_dict["password"] = user.password

    result = await db.user_profiles.insert_one(user_dict)
    user_profile = await get_user_profile(result.inserted_id)

    access_token, access_token_expiration = create_access_token({"sub": user.username})
    refresh_token = create_refresh_token({"sub": user.username})

    refresh_token_data = {
        "username": user.username,
        "refresh_token": refresh_token,
        "access_token_expiration": access_token_expiration,
        "created_at": datetime.utcnow()
    }

    existing_token = await db.refresh_tokens.find_one({"username": user.username})
    if existing_token:
        await db.refresh_tokens.update_one(
            {"username": user.username},
            {"$set": refresh_token_data}
        )
    else:
        await db.refresh_tokens.insert_one(refresh_token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expiration=access_token_expiration
    )


@router.post("/login/", response_model=TokenResponse)
async def login(form_data: UserLogin):
    user = await db.user_profiles.find_one({"username": form_data.username})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.get("password") or not await verify_password(form_data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_profile = await get_user_profile(user["_id"])

    access_token, access_token_expiration = create_access_token({"sub": form_data.username})
    refresh_token = create_refresh_token({"sub": form_data.username})

    refresh_token_data = {
        "username": form_data.username,
        "refresh_token": refresh_token,
        "access_token_expiration": access_token_expiration,  # Сохраняем срок действия
        "created_at": datetime.utcnow()
    }

    existing_token = await db.refresh_tokens.find_one({"username": form_data.username})
    if existing_token:
        await db.refresh_tokens.update_one(
            {"username": form_data.username},
            {"$set": refresh_token_data}
        )
    else:
        await db.refresh_tokens.insert_one(refresh_token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expiration=access_token_expiration
    )


@router.post("/logout/")
async def logout(refresh_token: str):
    token_data = await db.refresh_tokens.find_one({"refresh_token": refresh_token})
    if not token_data:
        raise HTTPException(status_code=404, detail="Invalid refresh token")

    username = token_data["username"]
    refresh_token_result = await db.refresh_tokens.delete_one({"refresh_token": refresh_token})

    if refresh_token_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Refresh token not found")
    return {"detail": "Successfully logged out"}


@router.post("/refresh/", response_model=TokenResponse)
async def refresh(request: RefreshTokenRequest):
    refresh_token = request.refresh_token
    token_data = await db.refresh_tokens.find_one({"refresh_token": refresh_token})
    if not token_data:
        raise HTTPException(status_code=404, detail="Invalid refresh token")
    if token_data["access_token_expiration"] < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Access token has expired")

    username = token_data.get("username")
    access_token, access_token_expiration = create_access_token({"sub": username})
    new_refresh_token = create_refresh_token({"sub": username})

    await db.refresh_tokens.update_one(
        {"refresh_token": refresh_token},
        {"$set": {
            "refresh_token": new_refresh_token,
            "access_token_expiration": access_token_expiration
        }}
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        access_token_expiration=access_token_expiration
    )


@router.get("/user/", response_model=List[UserProfile])
async def list_user(current_user: dict = Depends(get_current_user)):
    user_profiles = await db.user_profiles.find({"_id": ObjectId(current_user["_id"])}).to_list(100)
    return [UserProfile(**profile) for profile in user_profiles]


@router.get("/user-profiles/", response_model=List[UserProfile])
async def list_user_profiles():
    user_profiles = await db.user_profiles.find().to_list()
    return user_profiles


@router.get("/user-profile/{user_id}", response_model=UserProfile)
async def read_user_profile(user_id: str):
    user_profiles = await db.user_profiles.find_one({"_id": ObjectId(user_id)})
    if user_profiles:
        return user_profiles
    raise HTTPException(status_code=404, detail="User not found")


# CRUD for Presentations
@router.post("/presentations/", response_model=Presentations)
async def create_presentation(presentation: Presentations):
    presentation_dict = presentation.dict()
    result = await db.presentations.insert_one(presentation_dict)
    if result.inserted_id:
        presentation_dict["_id"] = result.inserted_id
        return presentation_dict
    raise HTTPException(status_code=400, detail="Presentation not created")


@app.get("/presentations/", response_model=List[Presentations])
async def list_presentations():
    presentations = await db.presentations.find().to_list()
    return presentations


@router.get("/presentations/{presentation_id}", response_model=Presentations)
async def read_presentation(presentation_id: str):
    presentation = await db.presentations.find_one({"_id": ObjectId(presentation_id)})
    if presentation:
        return presentation
    raise HTTPException(status_code=404, detail="Presentation not found")


@router.put("/presentations/{presentation_id}", response_model=Presentations)
async def update_presentation(presentation_id: str, presentation: Presentations):
    updated_presentation = await db.presentations.update_one(
        {"_id": ObjectId(presentation_id)}, {"$set": presentation.dict()}
    )
    if updated_presentation.modified_count:
        return await read_presentation(presentation_id)
    raise HTTPException(status_code=404, detail="Presentation not found")


@router.delete("/presentations/{presentation_id}")
async def delete_presentation(presentation_id: str):
    delete_result = await db.presentations.delete_one({"_id": ObjectId(presentation_id)})
    if delete_result.deleted_count:
        return {"message": "Presentation deleted"}
    raise HTTPException(status_code=404, detail="Presentation not found")


# CRUD for Purchases
@router.post("/purchases/", response_model=Purchases)
async def create_purchase(purchase: Purchases):
    await check_document_exists(db.user_profiles, purchase.user_id)
    await check_document_exists(db.presentations, purchase.presentation_id)

    purchase_dict = purchase.dict()
    purchase_dict["purchase_date"] = datetime.now()
    result = await db.purchases.insert_one(purchase_dict)
    if result.inserted_id:
        purchase_dict["_id"] = result.inserted_id
        return purchase_dict
    raise HTTPException(status_code=400, detail="Purchase not created")


@router.get("/purchases/{purchase_id}", response_model=Purchases)
async def read_purchase(purchase_id: str):
    purchase = await db.purchases.find_one({"_id": ObjectId(purchase_id)})
    if purchase:
        return purchase
    raise HTTPException(status_code=404, detail="Purchase not found")


@app.get("/purchases/", response_model=List[Purchases])
async def list_purchases():
    purchases = await db.purchases.find().to_list()
    return purchases


@router.get("/purchases/user/{user_id}", response_model=List[Purchases])
async def read_purchases_by_user(user_id: str):
    purchases = await db.purchases.find({"user_id": user_id}).to_list(100)
    return purchases


@router.delete("/purchases/{purchase_id}")
async def delete_purchase(purchase_id: str):
    delete_result = await db.purchases.delete_one({"_id": ObjectId(purchase_id)})
    if delete_result.deleted_count:
        return {"message": "Purchase deleted"}
    raise HTTPException(status_code=404, detail="Purchase not found")


# CRUD for Subscription
@router.post("/subscriptions/", response_model=Subscription)
async def create_subscription(subscription: Subscription):
    await check_document_exists(db.user_profiles, subscription.user_id)

    subscription_dict = subscription.dict()
    result = await db.subscriptions.insert_one(subscription_dict)
    if result.inserted_id:
        subscription_dict["_id"] = result.inserted_id
        return subscription_dict
    raise HTTPException(status_code=400, detail="Subscription not created")


@app.get("/subscriptions/", response_model=List[Subscription])
async def list_subscriptions():
    subscriptions = await db.subscriptions.find().to_list()
    return subscriptions


@router.get("/subscriptions/{subscription_id}", response_model=Subscription)
async def read_subscription(subscription_id: str):
    subscription = await db.subscriptions.find_one({"_id": ObjectId(subscription_id)})
    if subscription:
        return subscription
    raise HTTPException(status_code=404, detail="Subscription not found")


@router.put("/subscriptions/{subscription_id}", response_model=Subscription)
async def update_subscription(subscription_id: str, subscription: Subscription):
    updated_subscription = await db.subscriptions.update_one(
        {"_id": ObjectId(subscription_id)}, {"$set": subscription.dict()}
    )
    if updated_subscription.modified_count:
        return await read_subscription(subscription_id)
    raise HTTPException(status_code=404, detail="Subscription not found")


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str):
    delete_result = await db.subscriptions.delete_one({"_id": ObjectId(subscription_id)})
    if delete_result.deleted_count:
        return {"message": "Subscription deleted"}
    raise HTTPException(status_code=404, detail="Subscription not found")


@app.websocket("/ws/chat/")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Получаем сообщение от пользователя
            user_message = await websocket.receive_text()

            try:
                # Формируем запрос к API AI (stream: False)
                payload = {
                    "model": "models/Qwen/Qwen2.5-3B-Instruct",
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": user_message}
                    ],
                    "max_tokens": 2048,
                    "stream": False  # Отключаем потоковую передачу
                }

                # Отправляем запрос в API AI
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://051e-92-62-70-2.ngrok-free.app/v1/chat/completions",
                        headers={"Content-Type": "application/json"},
                        json=payload,
                        timeout=10.0  # Таймаут для запроса
                    )

                    # Проверяем статус ответа
                    if response.status_code != 200:
                        await websocket.send_text("Ваш LLM не работает")
                        continue

                    # Парсим ответ от API AI
                    response_data = response.json()
                    if "choices" in response_data and len(response_data["choices"]) > 0:
                        # Извлекаем полный ответ
                        full_response = response_data["choices"][0]["message"]["content"]
                        await websocket.send_text(full_response)
                    else:
                        await websocket.send_text("Некорректный формат ответа от AI")

            except httpx.RequestError:
                # Если API недоступен (например, нет сети или сервер упал)
                await websocket.send_text("Ваш LLM не работает")
            except Exception as e:
                # Ловим другие ошибки (например, проблемы с JSON)
                await websocket.send_text(f"Произошла ошибка: {str(e)}")

    except WebSocketDisconnect:
        # Обработка отключения пользователя
        await websocket.close()


@router.post("/generate-slide/", operation_id="generate_slide")
async def generate_slide(request: Request, slide_request: SlideRequest):
    try:
        body = await request.json()
        print("Received request with body:", body)  # Логируем входящие данные
    except Exception as e:
        print("Failed to parse JSON body:", str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    keyword = slide_request.keyword
    count = slide_request.count

    if count not in [1, 2]:
        raise HTTPException(status_code=400, detail="Количество слайдов должно быть 1 или 2")

    # Генерация данных для слайда (заглушка)
    first_slide_data = {
        "keyword": keyword,
        "title": f"Title for {keyword}",
        "description": f"Description for {keyword}",
        "image_url": "https://example.com/image.jpg",
        "created_at": datetime.now()
    }

    # Сохраняем слайд в MongoDB (заглушка)
    first_slide = await collections.insert_one(first_slide_data)
    first_slide_id = str(first_slide.inserted_id)  # Преобразуем ObjectId в строку

    response_data = {
        "first_slide": {**first_slide_data, "id": first_slide_id}
    }

    if count == 2:
        # Генерация данных для второго слайда (заглушка)
        second_slide_data = {
            "keyword": keyword,
            "title": f"Second Title for {keyword}",
            "description": f"Second Description for {keyword}",
            "image_url": "https://example.com/image2.jpg",
            "created_at": datetime.now()
        }

        # Сохраняем второй слайд в MongoDB (заглушка)
        second_slide = await collections.insert_one(second_slide_data)
        second_slide_id = str(second_slide.inserted_id)  # Преобразуем ObjectId в строку

        response_data["second_slide"] = {**second_slide_data, "id": second_slide_id}

    return response_data

# Эндпоинт для получения всех слайдов
@router.get("/get-slides/", operation_id="get_slides")
async def get_slides():
    slides = []
    async for slide in collections.find():
        slide["_id"] = str(slide["_id"])  # Преобразуем ObjectId в строку
        slides.append(slide)
    return {"slides": slides}



@router.get("/get-slide/")
async def get_slide(keyword: str, count: int = 1):
    if count not in [1, 2]:
        raise HTTPException(status_code=400, detail="Количество слайдов должно быть 1 или 2")

    # Получаем первый слайд
    first_slide = await collections.find_one({"keyword": keyword})
    if not first_slide:
        raise HTTPException(status_code=404, detail="Слайды не найдены")

    response_data = {
        "first_slide": {**first_slide, "id": str(first_slide["_id"])}
    }

    if count == 2:
        # Получаем второй слайд по ключевому слову
        second_slide = await collections.find_one({"keyword": keyword, "_id": {"$ne": first_slide["_id"]}})
        if not second_slide:
            raise HTTPException(status_code=404, detail="Второй слайд не найден")

        response_data["second_slide"] = {**second_slide, "id": str(second_slide["_id"])}

    return response_data

app.include_router(router)




