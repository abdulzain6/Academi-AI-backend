from pydantic import BaseModel

class AIModel(BaseModel):
    regular_model: object
    regular_args: dict
    premium_model: object
    premium_args: dict

