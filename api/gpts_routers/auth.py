from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from api.config import GPT_API_KEY
from fastapi import Depends, HTTPException, status

security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if credentials.credentials == GPT_API_KEY:
        return 
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )