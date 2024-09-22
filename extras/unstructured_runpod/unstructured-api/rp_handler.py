from langchain_community.document_loaders import UnstructuredFileIOLoader
from rp_schema import INPUT_VALIDATIONS
from runpod.serverless.utils.rp_validator import validate
from runpod.serverless.utils import download_files_from_urls, rp_cleanup, rp_debugger

import io
import requests
import runpod


API_URL = "http://localhost:8000/"

def load_documents(file_link: str, mode: str = "single", **unstructured_args) -> list[dict]:
    print("DOwnloading file")
    response = requests.get(file_link)
    response.raise_for_status()
    io_object = io.BytesIO(response.content)
    print("file downloaded")
    loader = UnstructuredFileIOLoader(
        file=io_object,
        mode=mode,
        **unstructured_args
    )
    docs = loader.load()
    print("File loaded, returning docs")
    return [{"content" : doc.page_content, "metadata" : doc.metadata} for doc in docs]
    
    
def handler(job):
    '''
    This is the handler function that will be called on every job.
    '''
    job_input = job['input']
    with rp_debugger.LineTimer('validation_step'):
        input_validation = validate(job_input, INPUT_VALIDATIONS)

        if 'errors' in input_validation:
            return {"error": input_validation['errors']}
        job_input = input_validation['validated_input']
        
    with rp_debugger.LineTimer('run_pipeline'):
        docs = load_documents(job_input["file_link"], job_input["mode"], **job_input["unstructured_args"])
    
    with rp_debugger.LineTimer('cleanup_step'):
        rp_cleanup.clean(['input_objects'])
        
    return docs


runpod.serverless.start({"handler": handler})