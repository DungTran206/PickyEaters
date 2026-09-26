from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TaskObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["Main", "Drink", "Side"]
    concept: Optional[str] = None
    required: bool = True


class HardConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_min: Optional[int] = None
    price_max: Optional[int] = None
    spicy: Optional[bool] = None


class SoftPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cuisine_affinity: List[str] = Field(default_factory=list)
    priority_order: List[Literal["price", "distance", "rating", "promotion"]] = Field(default_factory=list)


class SemanticAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    strength: Literal["hard", "soft"] = "soft"
    target: Literal["object", "order"]


class Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["same_order", "same_restaurant"]
    objects: List[int]


class FollowUp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["reject_previous", "refine", "new_request"]
    reason: Optional[str] = None


class TaskContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    party_size: int = 1
    conversation_ref: Optional[str] = None

    @field_validator("conversation_ref", mode="before")
    @classmethod
    def ordinal_as_string(cls, value):
        # LLMs often emit the ordinal as a number (2) instead of a string ("2").
        return str(value) if isinstance(value, int) and not isinstance(value, bool) else value


class TaskModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["request_recommendation", "state_preference", "provide_info", "chit_chat"]
    objects: List[TaskObject] = Field(default_factory=list)
    hard_constraints: HardConstraints = Field(default_factory=HardConstraints)
    ingredient_excludes: List[str] = Field(default_factory=list)
    soft_preferences: SoftPreferences = Field(default_factory=SoftPreferences)
    excluded_concepts: List[str] = Field(default_factory=list)
    semantic_attributes: List[SemanticAttribute] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    follow_up: Optional[FollowUp] = None
    context: TaskContext = Field(default_factory=TaskContext)

    @model_validator(mode="after")
    def validate_references(self):
        count = len(self.objects)
        for relationship in self.relationships:
            if len(relationship.objects) < 2:
                raise ValueError("relationships must reference at least two objects")
            if any(index < 0 or index >= count for index in relationship.objects):
                raise ValueError("relationship object index is out of range")
        if self.context.party_size < 1:
            raise ValueError("party_size must be at least 1")
        if self.hard_constraints.price_min is not None and self.hard_constraints.price_min < 0:
            raise ValueError("price_min cannot be negative")
        if self.hard_constraints.price_max is not None and self.hard_constraints.price_max < 0:
            raise ValueError("price_max cannot be negative")
        if (
            self.hard_constraints.price_min is not None
            and self.hard_constraints.price_max is not None
            and self.hard_constraints.price_min > self.hard_constraints.price_max
        ):
            raise ValueError("price_min cannot exceed price_max")
        return self
