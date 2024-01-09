from fastapi import APIRouter, Depends, HTTPException
from ..globals import plantuml_server
from .auth import verify_token
from pydantic import BaseModel, Field
from api.globals import redis_cache_manager, CACHE_IMAGE_URL_TEMPLATE, mermaid_client
from api.lib.tools import make_vega_graph, make_graphviz_graph
import uuid

router = APIRouter()

class MakeUMLRequest(BaseModel):
    plantuml_code: str = Field(description="Plantuml code for the uml diagram to create")
    
class MakeVegaLiteGraphRequest(BaseModel):
    vegalite_code: str = Field(description="Vega Lite code for the diagram to create")

class MakeGraphvizDiagramRequest(BaseModel):
    graphviz_code: str = Field(description="Graphviz dot code for the diagram to create")

class MakeMermaidDiagramRequest(BaseModel):
    mermaid_code: str = Field(description="Mermaid diagram code for the diagram to create")
    diagram_type: str = Field(default='png', description="Type of diagram to return (png or svg)")


@router.post("/make_gz_diagram", description="Makes Diagram using graphviz code", openapi_extra={"x-openai-isConsequential": False})
def make_gz_diagram(
    make_gz_request: MakeGraphvizDiagramRequest,
    _=Depends(verify_token),
):     
    try:
        return make_graphviz_graph(make_gz_request.graphviz_code, cache_manager=redis_cache_manager, url_template=CACHE_IMAGE_URL_TEMPLATE)
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    
@router.post("/make_vgl_diagram", description="Makes Diagram using vegalite code", openapi_extra={"x-openai-isConsequential": False})
def make_vgl_diagram(
    make_vgl_request: MakeVegaLiteGraphRequest,
    _=Depends(verify_token),
):     
    try:
        return make_vega_graph(make_vgl_request.vegalite_code, cache_manager=redis_cache_manager, url_template=CACHE_IMAGE_URL_TEMPLATE)
    except Exception as e:
        raise HTTPException(400, detail=str(e))

@router.post("/make_uml", description="Makes uml using plantuml code", openapi_extra={"x-openai-isConsequential": False})
def make_uml(
    make_uml_request: MakeUMLRequest,
    _=Depends(verify_token),
):     
    try:
        rand_id = str(uuid.uuid4()) + ".png"
        img_bytes = plantuml_server.processes(make_uml_request.plantuml_code)
        redis_cache_manager.set(key=rand_id, value=img_bytes, ttl=18000, suppress=False)
        document_url = CACHE_IMAGE_URL_TEMPLATE.format(doc_id=rand_id)
        return f"Diagram available at: {document_url}. Give the following link as it is to the user dont add sandbox prefix to it {document_url}. "
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    

@router.post("/make_mm_diagram", description="Makes UML using Mermaid code", openapi_extra={"x-openai-isConsequential": False})
def make_mm(
    make_mermaid_request: MakeMermaidDiagramRequest,
    _=Depends(verify_token),
):
    try:
        rand_id = str(uuid.uuid4()) + f".{make_mermaid_request.diagram_type}"
        img_bytes = mermaid_client.get_diagram_image(make_mermaid_request.mermaid_code, image_type=make_mermaid_request.diagram_type)
        redis_cache_manager.set(key=rand_id, value=img_bytes, ttl=18000, suppress=False)
        document_url = CACHE_IMAGE_URL_TEMPLATE.format(doc_id=rand_id)
        return f"Diagram available at: {document_url}. Give the following link as it is to the user don't add sandbox prefix to it {document_url}. "
    except Exception as e:
        raise HTTPException(400, detail=str(e))