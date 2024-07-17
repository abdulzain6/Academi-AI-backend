from fastapi import HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from ..globals import RAPID_API_KEY

security = HTTPBearer()

def verify_rapidapi_key(header: HTTPAuthorizationCredentials = Depends(security)):
    try:
        if header.credentials == RAPID_API_KEY:
            return
        else:
            raise ValueError("Wrong key")
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e)) from e