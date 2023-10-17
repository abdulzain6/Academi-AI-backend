from fastapi import FastAPI
from .config import *
from .routers.collections import router as collection_router
from .routers.files import router as files_router
from .routers.users import router as users_router
from .routers.chat import router as chat_router
from .routers.presentation import router as presentation_router
from .routers.conversations import router as convo_router
from .routers.quiz import router as quiz_router
from .routers.maths_solver import router as maths_solver_routers
from .routers.writer import router as writer_router
import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.status import HTTP_504_GATEWAY_TIMEOUT
import langchain
import logging

langchain.verbose = False
logging.basicConfig(level=logging.INFO)


app = FastAPI()


app.include_router(users_router, prefix="/api/v1/users", tags=["user"])
app.include_router(files_router, prefix="/api/v1/files", tags=["files"])
app.include_router(collection_router, prefix="/api/v1/collections", tags=["collections"])
app.include_router(presentation_router, prefix="/api/v1/presentation", tags=["presentation"])
app.include_router(chat_router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(convo_router, prefix="/api/v1/conversations", tags=["conversations"])
app.include_router(quiz_router, prefix="/api/v1/quiz", tags=["quiz"])
app.include_router(maths_solver_routers, prefix="/api/v1/maths_solver", tags=["maths solver"])
app.include_router(writer_router, prefix="/api/v1/writer", tags=["writer"])


@app.get("/")
def hello():
    return "hello"

@app.middleware('http')
async def timeout_middleware(request: Request, call_next):
    try:
        return await asyncio.wait_for(call_next(request), timeout=REQUEST_TIMEOUT)
    except asyncio.TimeoutError:
        return JSONResponse(
            {'detail': 'Request exceeded the time limit for processing'},
            status_code=HTTP_504_GATEWAY_TIMEOUT,
        )