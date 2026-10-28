from fastapi import APIRouter
from app.api.v1.routes import health, predict, chat, rag, items, users, documents

api_router = APIRouter()

# AI & ML routes
api_router.include_router(health.router)
api_router.include_router(chat.router)
api_router.include_router(rag.router)
api_router.include_router(predict.router)

# Document Intelligence Platform routes
api_router.include_router(documents.router)

# Traditional Web API routes
api_router.include_router(users.router)
api_router.include_router(items.router)
