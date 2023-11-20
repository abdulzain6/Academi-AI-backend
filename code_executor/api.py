from fastapi import FastAPI
from pydantic import BaseModel
from code_executor import FinalStatefulSafeCodeEvaluator  # Assuming you have this module
import asyncio

app = FastAPI()

math_libraries = [
    "math",  # Basic mathematical functions and constants
    "numpy",  # Numerical computing and arrays
    "scipy",  # Scientific computing and optimization
    "sympy",  # Symbolic mathematics
    "statsmodels",  # Statistical models
    "networkx",  # Network analysis
    "cvxpy",  # Convex optimization
    "gmpy2",  # Arbitrary-precision arithmetic
    "mpmath",  # Arbitrary-precision floating-point arithmetic
    "pyomo",  # Optimization modeling
    "qiskit",  # Quantum computing
    "shapely",  # Geometric objects, predicates, and operations
    "numexpr",  # Fast numerical expression evaluation
    "cmath",
    "statistics",
    "pandas"
]


evaluator = FinalStatefulSafeCodeEvaluator(math_libraries)

class EvaluateRequest(BaseModel):
    code: str
    timeout: int

class EvaluateResponse(BaseModel):
    success: bool
    result: str

async def evaluate(code: str, timeout: int) -> EvaluateResponse:
    loop = asyncio.get_event_loop()
    try:
        success, result = await asyncio.wait_for(
            loop.run_in_executor(None, evaluator.evaluate, code), 
            timeout=timeout
        )
        print(result)
        return EvaluateResponse(success=True, result=str(result))
    except asyncio.TimeoutError:
        return EvaluateResponse(success=False, result="Evaluation timed out")

@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_code(request: EvaluateRequest) -> EvaluateResponse:
    return await evaluate(request.code, request.timeout)

@app.get("/allowed_libraries")
async def get_allowed_libraries():
    libraries = evaluator.get_allowed_libraries()
    return {"libraries": libraries}
