import sys
from pathlib import Path

from sqlalchemy import select

API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.security import hash_password
from app.db.models import (
    EnzymeFamily,
    EnzymeModule,
    Project,
    ProjectMember,
    ProjectMemberRole,
    User,
    UserRole,
)
from app.db.session import get_session_local


DEMO_EMAIL = "demo@iee.local"
DEMO_PASSWORD = "demo-password"
DEMO_USER_EMAIL = "user@iee.local"
DEMO_USER_PASSWORD = "user-password"


def upsert_family(session, module: EnzymeModule, name: str, description: str) -> EnzymeFamily:
    family = session.scalar(select(EnzymeFamily).where(EnzymeFamily.module == module))
    if family is None:
        family = EnzymeFamily(module=module, name=name, description=description)
        session.add(family)
    else:
        family.name = name
        family.description = description
    return family


def upsert_user(
    session,
    *,
    email: str,
    password: str,
    display_name: str,
    role: UserRole,
) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
            role=role,
        )
        session.add(user)
        session.flush()
    else:
        user.display_name = display_name
        user.role = role
    return user


def upsert_owned_project(
    session,
    *,
    owner: User,
    name: str,
    description: str,
    target_enzyme_module: EnzymeModule,
) -> Project:
    project = session.scalar(
        select(Project).where(Project.owner_user_id == owner.id, Project.name == name)
    )
    if project is None:
        project = Project(
            owner_user_id=owner.id,
            name=name,
            description=description,
            target_enzyme_module=target_enzyme_module,
        )
        session.add(project)
        session.flush()
    else:
        project.description = description
        project.target_enzyme_module = target_enzyme_module

    membership = session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == owner.id,
        )
    )
    if membership is None:
        session.add(
            ProjectMember(
                project_id=project.id,
                user_id=owner.id,
                role=ProjectMemberRole.OWNER,
            )
        )
    elif membership.role != ProjectMemberRole.OWNER:
        membership.role = ProjectMemberRole.OWNER
    return project


def main() -> None:
    session_factory = get_session_local()
    with session_factory() as session:
        admin_user = upsert_user(
            session,
            email=DEMO_EMAIL,
            password=DEMO_PASSWORD,
            display_name="IEE Demo Admin",
            role=UserRole.ADMIN,
        )
        regular_user = upsert_user(
            session,
            email=DEMO_USER_EMAIL,
            password=DEMO_USER_PASSWORD,
            display_name="IEE Demo User",
            role=UserRole.USER,
        )

        upsert_family(
            session,
            EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE,
            "Anthraquinone glycosyltransferases",
            "Anthraquinone substrate glycosylation engineering targets.",
        )
        upsert_family(
            session,
            EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            "Mature microbial transglutaminases",
            "Mature microbial transglutaminase engineering targets.",
        )

        upsert_owned_project(
            session,
            owner=admin_user,
            name="Demo admin project",
            description="Seed project for curator and administrator evaluation.",
            target_enzyme_module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        )
        upsert_owned_project(
            session,
            owner=regular_user,
            name="Demo user project",
            description="Seed project for regular user wet-lab data submission.",
            target_enzyme_module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
        )

        session.commit()


if __name__ == "__main__":
    main()
