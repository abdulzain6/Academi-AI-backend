from .firebase import default_app # Important
from prometheus_fastapi_instrumentator import Instrumentator
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
from .routers.summary_writer import router as summary_router
from .routers.subscriptions_playstore import router as playstore_sub_router
from .routers.subscriptions import router as subscriptions_router
from .routers.cv_maker import router as cv_router
from .routers.notes_maker import router as notes_router
from .routers.grammar_checker import router as grammar_router
from .routers.tools import router as tool_router
from .routers.uml import router as uml_router
from .routers.info import router as info_router
from .routers.assignment_maker import router as assignment_router
from .routers.text_to_handwritting import router as handwriting_router
from .routers.infographic_maker import router as infographic_router
from .routers.free_courses import router as courses_router

#gpts
from api.gpts_routers.resume import router as gpt_resume_router
from api.gpts_routers.uml import router as gpts_uml_router
from api.gpts_routers.notes import router as notes_router_gpt

#course radar
from api.course_radar.courses import router as course_radar_search_router

#rapid api
from api.rapid_api.courses import router as rapid_api_courses_router

from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBasicCredentials, HTTPBasic
from starlette.status import HTTP_504_GATEWAY_TIMEOUT
from fastapi.middleware.cors import CORSMiddleware



import asyncio
import langchain
import logging
import secrets
from .globals import (
    DOCS_PASSWORD,
    DOCS_USERNAME,
    APP_DOMAIN
)

langchain.verbose = True
logging.basicConfig(level=logging.INFO)


app = FastAPI(
    title="Academi.AI",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)
    
security = HTTPBasic()

def verify_prometheus(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, PROM_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, PROM_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

try:
    Instrumentator().instrument(app).expose(app, include_in_schema=False, dependencies=[Depends(verify_prometheus)])
except Exception as e:
    logging.error(f"Error in instrumenting app {e}")

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, DOCS_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, DOCS_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@app.get("/docs", include_in_schema=False)
async def get_swagger_documentation(username: str = Depends(get_current_username)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="docs")

@app.get("/redoc", include_in_schema=False)
async def get_redoc_documentation(username: str = Depends(get_current_username)):
    return get_redoc_html(openapi_url="/openapi.json", title="docs")

@app.get("/openapi.json", include_in_schema=False)
async def openapi(username: str = Depends(get_current_username)):
    return get_openapi(title=app.title, version=app.version, routes=app.routes)

@app.get("/health")
async def health():
    return {"health" : "mama-mia"}

@app.get("/gpts/privacy-policy/")
def privacy_policy():
    return """
Privacy Policy
==============

**1. No Data Collection**
We do not collect any personal data from our users. Our service is designed to respect your privacy and the confidentiality of your information.

**2. Data Processing**
Any data provided by users for processing (e.g., files, images, etc.) is used solely for the purpose of the provided service. We do not use this data for any other purpose.

**3. Data Removal**
All data provided by users is automatically removed from our systems immediately after processing. We do not store any user data beyond the duration necessary to provide our services.

**4. No Data Sharing**
We do not share any data with third parties. Your data is your own and is treated with the utmost confidentiality.

**5. Contact Information**
If you have any questions or concerns about our privacy practices, please contact us at [Your Contact Information].

We reserve the right to modify this privacy policy at any time, so please review it frequently. Changes and clarifications will take effect immediately upon their posting on the website.
"""

@app.get("/gpts/get-openapi-schema/")
def get_openapi_schema():
    app_for_schema_generation = FastAPI()
    app_for_schema_generation.include_router(gpt_resume_router, prefix="/gpts/resume", tags=["gpts", "resume"])
    openapi_schema = app_for_schema_generation.openapi()
    openapi_schema["servers"] = [{"url": APP_DOMAIN}]
    return openapi_schema

@app.get("/gpts/notes/get-openapi-schema/")
def get_openapi_schema():
    app_for_schema_generation = FastAPI()
    app_for_schema_generation.include_router(notes_router_gpt, prefix="/gpts/notes", tags=["gpts", "notes"])
    openapi_schema = app_for_schema_generation.openapi()
    openapi_schema["servers"] = [{"url": APP_DOMAIN}]
    return openapi_schema

@app.get("/gpts/uml/get-openapi-schema/")
def get_openapi_schema():
    app_for_schema_generation = FastAPI()
    app_for_schema_generation.include_router(gpts_uml_router, prefix="/gpts/uml", tags=["gpts", "uml"])
    openapi_schema = app_for_schema_generation.openapi()
    openapi_schema["servers"] = [{"url": APP_DOMAIN}]
    return openapi_schema


app.include_router(users_router, prefix="/api/v1/users", tags=["user"])
app.include_router(files_router, prefix="/api/v1/files", tags=["files"])
app.include_router(collection_router, prefix="/api/v1/collections", tags=["collections"])
app.include_router(presentation_router, prefix="/api/v1/presentation", tags=["presentation"])
app.include_router(chat_router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(convo_router, prefix="/api/v1/conversations", tags=["conversations"])
app.include_router(quiz_router, prefix="/api/v1/quiz", tags=["quiz"])
app.include_router(maths_solver_routers, prefix="/api/v1/maths_solver", tags=["maths solver"])
app.include_router(writer_router, prefix="/api/v1/writer", tags=["writer"])
app.include_router(playstore_sub_router, prefix="/api/v1/subscriptions/playstore", tags=["playstore", "subscriptions"])
app.include_router(summary_router, prefix="/api/v1/summary", tags=["summary"])
app.include_router(subscriptions_router, prefix="/api/v1/subscriptions-info", tags=["subscriptions"])
app.include_router(cv_router, prefix="/api/v1/cv_maker", tags=["cv maker"])
app.include_router(notes_router, prefix="/api/v1/notes_maker", tags=["notes maker"])
app.include_router(grammar_router, prefix="/api/v1/grammar_checker", tags=["grammar checker"])
app.include_router(tool_router, prefix="/api/v1/tools", tags=["tools"])
app.include_router(uml_router, prefix="/api/v1/uml", tags=["uml"])
app.include_router(info_router, prefix="/api/v1/info", tags=["info"])
app.include_router(assignment_router, prefix="/api/v1/assignment", tags=["assignment"])
app.include_router(handwriting_router, prefix="/api/v1/handwriting", tags=["handwriting"])
app.include_router(infographic_router, prefix="/api/v1/infographic", tags=["infographic"])
app.include_router(courses_router, prefix="/api/v1/courses", tags=["courses"])


app.include_router(gpt_resume_router, prefix="/gpts/resume", tags=["gpts", "resume"])
app.include_router(gpts_uml_router, prefix="/gpts/uml", tags=["gpts", "uml"])
app.include_router(notes_router_gpt, prefix="/gpts/notes", tags=["gpts", "notes"])

app.include_router(course_radar_search_router, prefix="/course_radar/courses", tags=["course_radar"])
app.include_router(rapid_api_courses_router, prefix="/rapidapi/courses", tags=["rapid_api"])


@app.middleware('http')
async def timeout_middleware(request: Request, call_next):
    try:
        return await asyncio.wait_for(call_next(request), timeout=REQUEST_TIMEOUT)
    except asyncio.TimeoutError:
        return JSONResponse(
            {'detail': 'Request exceeded the time limit for processing'},
            status_code=HTTP_504_GATEWAY_TIMEOUT,
        )