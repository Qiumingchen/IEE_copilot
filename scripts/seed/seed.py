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


def upsert_family(session, module: EnzymeModule, name: str, description: str) -> EnzymeFamily:
    family = session.scalar(select(EnzymeFamily).where(EnzymeFamily.module == module))
    if family is None:
        family = EnzymeFamily(module=module, name=name, description=description)
        session.add(family)
    else:
        family.name = name
        family.description = description
    return family


def main() -> None:
    session_factory = get_session_local()
    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = User(
                email=DEMO_EMAIL,
                password_hash=hash_password(DEMO_PASSWORD),
                display_name="IEE Demo Admin",
                role=UserRole.ADMIN,
            )
            session.add(user)
            session.flush()

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

        project = session.scalar(
            select(Project).where(Project.owner_user_id == user.id, Project.name == "Demo project")
        )
        if project is None:
            project = Project(
                owner_user_id=user.id,
                name="Demo project",
                description="Seed project for IEE-Copilot evaluation.",
                target_enzyme_module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            )
            session.add(project)
            session.flush()
            session.add(
                ProjectMember(
                    project_id=project.id,
                    user_id=user.id,
                    role=ProjectMemberRole.OWNER,
                )
            )

        session.commit()


if __name__ == "__main__":
    main()
