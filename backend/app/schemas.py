from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
class ItemInput(Strict):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    location_id: int = Field(gt=0)
    category_id: int | None = None
    quantity: int = Field(default=1, ge=1)
    last_confirmed_at: datetime | None = None
class LocationInput(Strict):
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(default="space", min_length=1, max_length=50)
    parent_id: int | None = None
class MoveInput(Strict):
    to_location_id: int = Field(gt=0)
    note: str = Field(default="", max_length=2000)
