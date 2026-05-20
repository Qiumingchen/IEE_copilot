from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.models import (
    CurationStatus,
    Project,
    User,
    UserExperiment,
    Visibility,
    VisibilityRequest,
)
from app.db.session import get_db
from app.schemas.experiment import (
    UserExperimentResponse,
    VisibilityRequestCreate,
    VisibilityRequestResponse,
)


router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("/public", response_model=list[UserExperimentResponse])
def list_public_experiments(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[UserExperiment]:
    return list(
        db.scalars(
            select(UserExperiment)
            .where(
                UserExperiment.visibility == Visibility.PUBLIC,
                UserExperiment.curation_status == CurationStatus.APPROVED,
            )
            .order_by(UserExperiment.created_at)
        )
    )


@router.post(
    "/{experiment_id}/visibility-requests",
    response_model=VisibilityRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_visibility_request(
    experiment_id: str,
    request: VisibilityRequestCreate,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> VisibilityRequest:
    experiment = _get_owned_experiment(db, experiment_id, user.id)
    try:
        requested_visibility = Visibility(request.requested_visibility)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="unsupported requested_visibility",
        ) from exc
    if requested_visibility != Visibility.PUBLIC:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="only public visibility requests are supported",
        )

    existing_request = db.scalar(
        select(VisibilityRequest).where(
            VisibilityRequest.target_type == "user_experiment",
            VisibilityRequest.target_id == experiment.id,
            VisibilityRequest.requested_visibility == requested_visibility,
            VisibilityRequest.status == "pending",
        )
    )
    if existing_request is not None:
        experiment.curation_status = CurationStatus.PENDING
        db.commit()
        response.status_code = status.HTTP_200_OK
        return existing_request

    experiment.curation_status = CurationStatus.PENDING
    visibility_request = VisibilityRequest(
        project_id=experiment.project_id,
        target_type="user_experiment",
        target_id=experiment.id,
        requested_visibility=requested_visibility,
        status="pending",
        requested_by=user.id,
    )
    db.add(visibility_request)
    db.commit()
    db.refresh(visibility_request)
    return visibility_request


def _get_owned_experiment(db: Session, experiment_id: str, user_id: str) -> UserExperiment:
    row = db.execute(
        select(UserExperiment, Project)
        .join(Project, Project.id == UserExperiment.project_id)
        .where(
            UserExperiment.id == experiment_id,
            Project.owner_user_id == user_id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="experiment not found")
    experiment, _project = row
    return experiment
