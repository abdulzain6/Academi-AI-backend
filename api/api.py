from .config import *
from fastapi import FastAPI
from .routers.collections import router as collection_router
from .routers.files import router as files_router
from .routers.users import router as users_router
from .routers.chat import router as chat_router


app = FastAPI()

app.include_router(users_router, prefix="/api/v1/users")
app.include_router(files_router, prefix="/api/v1/files")
app.include_router(collection_router, prefix="/api/v1/collections")
app.include_router(chat_router, prefix="/api/v1/chat")