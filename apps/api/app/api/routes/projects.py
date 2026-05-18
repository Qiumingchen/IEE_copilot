from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.models import Project, ProjectMember, ProjectMemberRole, User
from app.db.session import get_db
from app.schemas.project import ProjectCreate, ProjectResponse


router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[Project]:
    return list(
        db.scalars(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user.id)
            .order_by(Project.created_at)
        )
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    request: ProjectCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Project:
    project = Project(
        owner_user_id=user.id,
        name=request.name,
        description=request.description,
        target_enzyme_module=request.target_enzyme_module,
        default_visibility=request.default_visibility,
    )
    db.add(project)
    db.flush()
    db.add(
        ProjectMember(
            project_id=project.id,
            user_id=user.id,
            role=ProjectMemberRole.OWNER,
        )
    )
    db.commit()
    db.refresh(project)
    return project
