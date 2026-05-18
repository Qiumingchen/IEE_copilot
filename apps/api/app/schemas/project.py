from pydantic import BaseModel, ConfigDict

from app.db.models import EnzymeModule, Visibility


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    target_enzyme_module: EnzymeModule | None = None
    default_visibility: Visibility = Visibility.PRIVATE


class ProjectResponse(BaseModel):
    id: str
    owner_user_id: str
    name: str
    description: str | None = None
    target_enzyme_module: EnzymeModule | None = None
    default_visibility: Visibility

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
