import logging
from fastapi import APIRouter, Depends, HTTPException, Response
from ..auth import get_user_id, verify_play_integrity
from ..lib.uml_diagram_maker import AIPlantUMLGenerator
from ..dependencies import require_points_for_feature, can_use_premium_model, get_model
from ..globals import plantuml_server

router = APIRouter()

@router.post("/make_uml")
@require_points_for_feature("UML")
def make_uml(
    prompt: str,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):     
    model_name, premium_model = can_use_premium_model(user_id=user_id)     
    model = get_model({"temperature": 0}, False, premium_model, alt=False)
    uml_maker = AIPlantUMLGenerator(model, generator=plantuml_server)
    logging.info(f"UML request from {user_id}, Data: {prompt}")
    
    try:
        img_bytes = uml_maker.run(prompt)
        return Response(content=img_bytes, media_type="image/png")
    except Exception as e:
        logging.error(f"Error in making uml diagram {e}")
        raise HTTPException(400, detail="AI was not able to make the diagram")
    
