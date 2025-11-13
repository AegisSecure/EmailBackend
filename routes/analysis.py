from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()
class TextIn(BaseModel):
    text: str
class TextListIn(BaseModel):
    texts: List[str]

@router.post("/analyze_sms_list")
async def analyze_sms_list(data: TextListIn,):
    print(f"Analyzing {len(data.texts)} messages...")
    
    return {"status": "success", "count": len(data.texts), "analysis": "placeholder_analysis"}
