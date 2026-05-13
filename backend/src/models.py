from pydantic import BaseModel
from typing import Optional

class ParseRequest(BaseModel):
    url: str
    local: Optional[bool] = False
    html: Optional[str] = None       # Aggiunto per il Grader del Prof!
    html_text: Optional[str] = None  # Mantenuto per il nostro frontend

class EvaluateRequest(BaseModel):
    parsed_text: str
    gold_text: str

class EvaluateJudgeRequest(BaseModel):
    url: str  
    parsed_text: str
    gold_text: str

class ResourceRequest(BaseModel):
    url: str
    html_text: Optional[str] = None
    gold_text: Optional[str] = None