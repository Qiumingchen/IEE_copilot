from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.models import Project, ProjectMember, ProjectMemberRole, User, UserExperiment
from app.db.session import get_db
from app.schemas.experiment import UserExperimentResponse
from app.schemas.project import ProjectCreate, ProjectResponse


router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[Project]:
    return list(
        db.scalars(
            select(Project).where(Project.owner_user_id == user.id).order_by(Project.created_at)
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


@router.get("/{project_id}/experiments", response_model=list[UserExperimentResponse])
def list_project_experiments(
    project_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[UserExperiment]:
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_user_id == user.id)
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

    return list(
        db.scalars(
            select(UserExperiment)
            .where(UserExperiment.project_id == project.id)
            .order_by(UserExperiment.created_at)
        )
    )
