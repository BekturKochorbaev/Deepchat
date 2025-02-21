from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi

uri = "mongodb+srv://avatarme05:Cp7hXiS6KXCUSHfl@deepchat.p7weg.mongodb.net/?retryWrites=true&w=majority&appName=Deepchat"

client = AsyncIOMotorClient(uri, server_api=ServerApi('1'))

db = client.deepchat_db
collections = db.deepchat_data


