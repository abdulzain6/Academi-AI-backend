from .config import *
from fastapi import FastAPI
from .routers.collections import router as collection_router
from .routers.files import router as files_router
from .routers.users import router as users_router
from .routers.chat import router as chat_router
from .routers.presentation import router as presentation_router
from .routers.conversations import router as convo_router
from .routers.quiz import router as quiz_router
from .routers.maths_solver import router as maths_solver_routers

import langchain

langchain.verbose = True

app = FastAPI()

app.include_router(users_router, prefix="/api/v1/users")
app.include_router(files_router, prefix="/api/v1/files")
app.include_router(collection_router, prefix="/api/v1/collections")
app.include_router(presentation_router, prefix="/api/v1/presentation")
app.include_router(chat_router, prefix="/api/v1/chat")
app.include_router(convo_router, prefix="/api/v1/conversations")
app.include_router(quiz_router, prefix="/api/v1/quiz")
app.include_router(maths_solver_routers, prefix="/api/v1/maths_solver")