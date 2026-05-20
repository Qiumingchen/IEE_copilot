from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.models import (
    AuditLog,
    CurationStatus,
    User,
    UserExperiment,
    UserRole,
    Visibility,
    VisibilityRequest,
)
from app.db.session import get_db
from app.schemas.experiment import (
    UserExperimentResponse,
    VisibilityRequestDetailResponse,
    VisibilityRequestReject,
    VisibilityRequestResponse,
)


router = APIRouter(prefix="/curation", tags=["curation"])


def curator_user(user: User = Depends(current_user)) -> User:
    if user.role not in {UserRole.CURATOR, UserRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="curator role required")
    return user


@router.get("/visibility-requests", response_model=list[VisibilityRequestDetailResponse])
def list_pending_visibility_requests(
    user: User = Depends(curator_user),
    db: Session = Depends(get_db),
) -> list[VisibilityRequestDetailResponse]:
    rows = db.execute(
        select(VisibilityRequest, UserExperiment)
        .join(UserExperiment, UserExperiment.id == VisibilityRequest.target_id)
        .where(
            VisibilityRequest.target_type == "user_experiment",
            VisibilityRequest.status == "pending",
        )
        .order_by(VisibilityRequest.created_at)
    ).all()
    return [_visibility_request_detail_response(request, experiment) for request, experiment in rows]


@router.post(
    "/visibility-requests/{request_id}/approve",
    response_model=VisibilityRequestResponse,
)
def approve_visibility_request(
    request_id: str,
    user: User = Depends(curator_user),
    db: Session = Depends(get_db),
) -> VisibilityRequest:
    request, experiment = _get_pending_visibility_request(db, request_id)
    now = datetime.now(UTC)
    request.status = "approved"
    request.reviewed_by = user.id
    request.reviewed_at = now
    experiment.visibility = Visibility.PUBLIC
    experiment.curation_status = CurationStatus.APPROVED
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="visibility_request.approve",
            target_type="visibility_request",
            target_id=request.id,
            metadata_json={"experiment_id": experiment.id},
        )
    )
    db.commit()
    db.refresh(request)
    return request


@router.post(
    "/visibility-requests/{request_id}/reject",
    response_model=VisibilityRequestResponse,
)
def reject_visibility_request(
    request_id: str,
    payload: VisibilityRequestReject,
    user: User = Depends(curator_user),
    db: Session = Depends(get_db),
) -> VisibilityRequest:
    review_comment = payload.review_comment.strip()
    if not review_comment:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="review_comment is required",
        )
    request, experiment = _get_pending_visibility_request(db, request_id)
    now = datetime.now(UTC)
    request.status = "rejected"
    request.reviewed_by = user.id
    request.reviewed_at = now
    request.review_comment = review_comment
    experiment.visibility = Visibility.PRIVATE
    experiment.curation_status = CurationStatus.REJECTED
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="visibility_request.reject",
            target_type="visibility_request",
            target_id=request.id,
            metadata_json={"review_comment": review_comment},
        )
    )
    db.commit()
    db.refresh(request)
    return request


def _get_pending_visibility_request(
    db: Session,
    request_id: str,
) -> tuple[VisibilityRequest, UserExperiment]:
    row = db.execute(
        select(VisibilityRequest, UserExperiment)
        .join(UserExperiment, UserExperiment.id == VisibilityRequest.target_id)
        .where(
            VisibilityRequest.id == request_id,
            VisibilityRequest.target_type == "user_experiment",
            VisibilityRequest.status == "pending",
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="visibility request not found")
    request, experiment = row
    return request, experiment


def _visibility_request_detail_response(
    request: VisibilityRequest,
    experiment: UserExperiment,
) -> VisibilityRequestDetailResponse:
    return VisibilityRequestDetailResponse(
        id=request.id,
        project_id=request.project_id,
        target_type=request.target_type,
        target_id=request.target_id,
        requested_visibility=request.requested_visibility.value,
        status=request.status,
        requested_by=request.requested_by,
        reviewed_by=request.reviewed_by,
        review_comment=request.review_comment,
        experiment=UserExperimentResponse.model_validate(experiment),
    )
