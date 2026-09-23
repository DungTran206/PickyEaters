import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from agent.agent import FoodAgent
from database.db import get_user_preferences, update_user_preference, reset_database
from database.models import UserPreference
from services.search import load_restaurants, load_menus, load_promotions

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(
    title="Personal Food Agent API",
    description="AI Food Recommendation Agent with Dynamic Radius (5km -> 10km) and Detailed Reasoning",
    version="2.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Personal Food Agent API is running."}


# Active agents mapped by user_id
AGENTS: Dict[str, FoodAgent] = {}


def get_agent_for_user(user_id: str) -> FoodAgent:
    if user_id not in AGENTS:
        AGENTS[user_id] = FoodAgent(user_id=user_id)
    return AGENTS[user_id]


class ChatRequest(BaseModel):
    message: str
    user_id: str = "user_01"
    user_name: Optional[str] = None
    user_address: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    tool_calls: List[Dict[str, Any]]
    user_id: str
    candidates: List[Dict[str, Any]] = []
    search_radius_km: float = 5.0
    is_radius_expanded: bool = False


class UserProfileRequest(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    district: Optional[str] = None


class UpdatePreferenceRequest(BaseModel):
    preference_type: str
    value: Any


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "restaurants_count": len(load_restaurants()),
        "dishes_count": len(load_menus()),
        "promotions_count": len(load_promotions())
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat_with_agent(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    agent = get_agent_for_user(req.user_id)
    result = agent.run(
        user_input=req.message,
        user_name=req.user_name,
        user_address=req.user_address
    )
    return ChatResponse(
        response=result["response"],
        tool_calls=result["tool_calls"],
        user_id=req.user_id,
        candidates=result.get("candidates", []),
        search_radius_km=result.get("search_radius_km", 5.0),
        is_radius_expanded=result.get("is_radius_expanded", False)
    )


@app.get("/api/user/{user_id}", response_model=UserPreference)
def get_user_profile(user_id: str):
    return get_user_preferences(user_id)


@app.post("/api/user/{user_id}", response_model=UserPreference)
def update_user_profile(user_id: str, req: UserProfileRequest):
    if req.name:
        update_user_preference(user_id, "name", req.name)
    if req.address:
        update_user_preference(user_id, "address", req.address)
    if req.district:
        update_user_preference(user_id, "district", req.district)
    return get_user_preferences(user_id)


@app.get("/api/preferences/{user_id}", response_model=UserPreference)
def get_preferences(user_id: str):
    return get_user_preferences(user_id)


@app.post("/api/preferences/{user_id}", response_model=UserPreference)
def set_preference(user_id: str, req: UpdatePreferenceRequest):
    return update_user_preference(user_id, req.preference_type, req.value)


@app.post("/api/reset-db")
def reset_db_endpoint():
    reset_database()
    AGENTS.clear()
    return {"status": "success", "message": "Database and agent memory reset."}
