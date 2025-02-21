from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, HTTPException, Depends
from config import collections, db
from database.models import UserProfile, TokenResponse, Subscription, Purchases, Presentations
from bson import ObjectId
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import timedelta, datetime
from views import get_user_profile, verify_password, check_document_exists, create_access_token, create_refresh_token
from typing import List

app = FastAPI(title="DeepChat")
router = APIRouter()


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
    access_token = create_access_token({"sub": user.username})
    refresh_token = create_refresh_token({"sub": user.username})

    refresh_token_data = {
        "username": user.username,
        "refresh_token": refresh_token,
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
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, token_type="bearer")


@router.post("/login/", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await db.user_profiles.find_one({"username": form_data.username})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.get("password") or not verify_password(form_data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_profile = await get_user_profile(user["_id"])
    access_token = create_access_token({"sub": form_data.username})
    refresh_token = create_refresh_token({"sub": form_data.username})
    refresh_token_data = {
        "username": form_data.username,
        "refresh_token": refresh_token,
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

    return TokenResponse(access_token=access_token, refresh_token=refresh_token, token_type="bearer")


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


@router.post("/refresh/")
async def refresh(refresh_token: str):
    token_data = await db.refresh_tokens.find_one({"refresh_token": refresh_token})

    if not token_data:
        raise HTTPException(status_code=404, detail="Invalid refresh token")
    access_token = create_access_token({"sub": token_data.get("username")})
    return {"access_token": access_token, "token_type": "bearer"}


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
app.include_router(router)






