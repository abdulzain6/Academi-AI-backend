from fastapi import APIRouter, Depends, HTTPException
from ..auth import get_user_id, verify_play_integrity
from ..lib.grammar_checker import GrammarChecker
from ..dependencies import require_points_for_feature, can_use_premium_model, get_model
from pydantic import BaseModel

router = APIRouter()

class Input(BaseModel):
    text: str


@router.post("/check_grammar")
@require_points_for_feature("GRAMMAR")
def check_grammar(
    input: Input,
    user_id=Depends(get_user_id),
    play_integrity_verified=Depends(verify_play_integrity),
):     
    if len(input.text) > 2500:
        raise HTTPException(400, detail="Text cannot be above 2500 characters")
    
    model_name, premium_model = can_use_premium_model(user_id=user_id)
    model = get_model({"temperature": 0.2}, False, premium_model)
    grammar_checker = GrammarChecker(model)
    return grammar_checker.check_grammar(input.text)