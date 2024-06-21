import os
import logging
import tempfile
import base64
from PIL import Image
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from api.lib.database.purchases import SubscriptionType
from api.lib.text_to_handwritting.text_to_handwritting import HandwritingRenderer, FONTS
from io import BytesIO
from api.globals import subscription_manager
from ..auth import get_user_id, verify_play_integrity
from ..dependencies import require_points_for_feature

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class TextToHandwritingRequest(BaseModel):
    text: str
    font_name: str
    font_size: int = 20
    ink_color: str = "black"
    paper_lines: bool = False
    transparent: bool = False
    noise_level: int = 20
    word_spacing: int = 60
    letter_spacing: int = 4
    background_image: str = None  # Base64 encoded image
    add_noise_effect: bool = True

def cleanup_temp_file(file_path: str):
    if os.path.exists(file_path):
        os.remove(file_path)
        
@router.get("/get-available-fonts")
def get_available_fonts(
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    try:
        return {"available_fonts": list(FONTS.keys())}
    except Exception as e:
        logger.error(f"Error fetching available fonts: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/text-to-handwriting-images")
def text_to_handwriting_images(
    request: TextToHandwritingRequest,
    background_tasks: BackgroundTasks,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    if subscription_manager.get_subscription_type(user_id) in {SubscriptionType.FREE}:
        raise HTTPException(status_code=400, detail="You must be subscribed to use this feature.")
    
    font_path = FONTS.get(request.font_name)
    if not font_path:
        raise HTTPException(status_code=400, detail="Font not found")

    background_image_path = None
    if request.background_image:
        try:
            # Decode the base64 image, convert with Pillow, and save it temporarily
            background_image_data = base64.b64decode(request.background_image)
            image = Image.open(BytesIO(background_image_data))
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                image.save(temp_file, format="PNG")
                background_image_path = temp_file.name
            background_tasks.add_task(cleanup_temp_file, background_image_path)
        except Exception as e:
            logger.error(f"Error processing background image: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid background image")

    renderer = HandwritingRenderer(
        font_path=font_path,
        font_size=request.font_size,
        ink_color=request.ink_color,
        paper_lines=request.paper_lines,
        transparent=request.transparent,
        noise_level=request.noise_level,
        word_spacing=request.word_spacing,
        letter_spacing=request.letter_spacing,
        background_image_path=background_image_path,
        add_noise_effect=request.add_noise_effect
    )

    try:
        images = renderer.render_text_to_handwriting(request.text)
        image_data = []
        for image in images:
            with BytesIO() as output:
                image.save(output, format="PNG")
                image_data.append(base64.b64encode(output.getvalue()).decode('utf-8'))
        return {"image_data": image_data}
    except ValueError as e:
        logger.error(f"Error generating handwriting images: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
            
    except Exception as e:
        logger.error(f"Error generating handwriting images: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/text-to-handwriting-pdf")
@require_points_for_feature("TEXT_TO_HANDWRITTING")
def text_to_handwriting_pdf(
    request: TextToHandwritingRequest,
    background_tasks: BackgroundTasks,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):
    if subscription_manager.get_subscription_type(user_id) in {SubscriptionType.FREE}:
        raise HTTPException(status_code=400, detail="You must be subscribed to use this feature.")
    
    font_path = FONTS.get(request.font_name)
    if not font_path:
        raise HTTPException(status_code=400, detail="Font not found")

    background_image_path = None
    if request.background_image:
        try:
            # Decode the base64 image, convert with Pillow, and save it temporarily
            background_image_data = base64.b64decode(request.background_image)
            image = Image.open(BytesIO(background_image_data))
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                image.save(temp_file, format="PNG")
                background_image_path = temp_file.name
            background_tasks.add_task(cleanup_temp_file, background_image_path)
        except Exception as e:
            logger.error(f"Error processing background image: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid background image")

    renderer = HandwritingRenderer(
        font_path=font_path,
        font_size=request.font_size,
        ink_color=request.ink_color,
        paper_lines=request.paper_lines,
        transparent=request.transparent,
        noise_level=request.noise_level,
        word_spacing=request.word_spacing,
        letter_spacing=request.letter_spacing,
        background_image_path=background_image_path,
        add_noise_effect=request.add_noise_effect
    )

    try:
        images = renderer.render_text_to_handwriting(request.text)
        pdf_bytes = renderer.save_images_to_pdf(images)
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        return {"pdf_data": pdf_base64}
    except ValueError as e:
        logger.error(f"Error generating handwriting images: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        logger.error(f"Error generating handwriting PDF: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")