import base64
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from api.globals import get_model
from api.lib.html_renderer import ImageExplainers
from api.lib.infographic_maker.infographic_maker import InfographicMaker
from langchain_core.messages import SystemMessage, HumanMessage
from ..auth import get_user_id, verify_play_integrity
from ..dependencies import can_use_premium_model, require_points_for_feature
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class InfographicRequest(BaseModel):
    markdown_content: str
    style: str
    border_color: str = 'black'
    border_width: int = 10

class RequestExplainer(BaseModel):
    prompt: str 
    
class GenerateWithAIRequest(BaseModel):
    topic: str
    
        
@router.get("/get-available-styles")
def get_available_styles(
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    try:
        return {"available_fonts": InfographicMaker().available_styles}
    except Exception as e:
        logger.error(f"Error fetching available fonts: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/make-infographic")
@require_points_for_feature("INFOGRAPHIC")
def make_infographic(
    request: InfographicRequest,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    if len(request.markdown_content) > 5000:
        raise HTTPException(400, detail="Content must be of maximum of 5000 characters")
    try:
        image = InfographicMaker().make_infographic(
            markdown=request.markdown_content,
            style=request.style,
            border_color=request.border_color,
            border_width=request.border_width
        )
        
        image_io = BytesIO()
        image.save(image_io, format='PNG')
        image_io.seek(0)
        
        return StreamingResponse(image_io, media_type="image/png")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating infographic: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    

@router.post("/generate_with_ai")
@require_points_for_feature("CHAT")
def generate_with_ai(
    request: GenerateWithAIRequest,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    try:
        model_name, premium_model = can_use_premium_model(user_id=user_id)
        llm = get_model({"temperature" : 0}, False, premium_model, alt=False)
        message = llm.invoke(
            [
                SystemMessage(content="""You are an AI designed to generate content for infographics in markdown
    The user will provide you with a topic you will generate the content based on that.
    Use emojis where appropriate
    The content must be one paragraph max. 30-50 words
    Get straight to the content and dont include phrases like 'Sure here is the content below'
                """),
                HumanMessage(content=f"""The content must be on {request.topic}. The content must be one paragraph max. 30-50 words\nThe content in markdown:""")
            ]
        )
        return {"generation" : message.content}
    except Exception as e:
        logging.error(f"Error: {e}")
        raise HTTPException(500, detail="Something went wrong, try again later!")
    
@router.post("/generate-image-explainer/")
@require_points_for_feature("IMAGE_EXPLAINERS")
def generate_images(
    request: RequestExplainer,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity)
):
    prompt = request.prompt
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required in the request body")
    try:
        styles = ["card", "card-purple", "student-card", "student-card-2", "student-card-3", "student-card-4", "student-card-5"]
        model_name, premium_model = can_use_premium_model(user_id=user_id)
        llm = get_model({"temperature" : 0}, False, premium_model, alt=False)

        imgs = ImageExplainers(
            llm,
            InfographicMaker(styles)
        ).run(prompt)
        
        base64_images = []
        for img in imgs:
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            base64_images.append(f"data:image/png;base64,{img_str}")
        
        return {"images": base64_images}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))