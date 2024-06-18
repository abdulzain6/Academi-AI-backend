import logging
from fastapi import APIRouter, Depends, HTTPException, Response

from api.lib.diagram_maker import DiagramMaker
from ..auth import get_user_id, verify_play_integrity
from ..dependencies import require_points_for_feature, can_use_premium_model, get_model_and_fallback
from ..globals import plantuml_server, mermaid_client

router = APIRouter()

@router.post("/make_uml")
@require_points_for_feature("UML")
def make_uml(
    prompt: str,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):     
    if len(prompt) > 2000:
        raise HTTPException(400, detail="Prompt must be of maximum 2000 characters.")
    
    model_name, premium_model = can_use_premium_model(user_id=user_id)     
    model, _ = get_model_and_fallback({"temperature": 0}, False, premium_model, alt=False)
    diagram_maker = DiagramMaker(mermaid_client, model, plantuml_server)
    logging.info(f"UML request from {user_id}, Data: {prompt}")
    
    try:
        img_bytes = diagram_maker.make_diagram(prompt)
        return Response(content=img_bytes, media_type="image/png")
    except Exception as e:
        logging.error(f"Error in making uml diagram {e}")
        raise HTTPException(400, detail="AI was not able to make the diagram, explain in more detail")
    
