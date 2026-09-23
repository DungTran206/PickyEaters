from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class UserPreference(BaseModel):
    user_id: str
    name: str = "Bạn"
    district: str = "Cầu Giấy"
    address: str = "Cầu Giấy, Hà Nội"
    preferred_cuisines: List[str] = Field(default_factory=list)
    preferred_flavors: List[str] = Field(default_factory=list)
    disliked_ingredients: List[str] = Field(default_factory=list)
    budget: int = 80000
    minimum_rating: float = 4.3
    preferred_distance: float = 5.0
    dietary_restrictions: List[str] = Field(default_factory=list)
    liked_dishes: List[str] = Field(default_factory=list)
    disliked_dishes: List[str] = Field(default_factory=list)
    updated_at: Optional[str] = None


class Restaurant(BaseModel):
    id: str
    name: str
    cuisine: str
    rating: float
    distance_km: float
    delivery_fee: int
    district: str = "Cầu Giấy"
    platform: str = "ShopeeFood"
    delivery_time_mins: int = 20
    address: str = ""
    open_hours: str = ""


class Dish(BaseModel):
    id: str
    restaurant_id: str
    name: str
    price: int
    spicy: bool = False
    cuisine: str = "Vietnamese"
    category: str = "Main"
    ingredients: List[str] = Field(default_factory=list)
    description: str = ""


class Promotion(BaseModel):
    id: str
    restaurant_id: str
    code: str
    type: str  # "discount" | "freeship" | "percent"
    value: float
    max_discount: float = 0
    minimum_order: float = 0
    description: str = ""


class PricingCalculation(BaseModel):
    original_price: int
    discount: int
    delivery_fee: int
    final_price: int
    applied_promotion_id: Optional[str] = None
    applied_promotion_code: Optional[str] = None
    savings: int = 0
    explanation: str = ""


class RecommendationCandidate(BaseModel):
    dish: Dish
    restaurant: Restaurant
    pricing: PricingCalculation
    scores: Dict[str, float] = Field(default_factory=dict)
    total_score: float = 0.0
    explanation: str = ""
    reasoning: str = ""
    search_radius_km: float = 5.0
    is_radius_expanded: bool = False

