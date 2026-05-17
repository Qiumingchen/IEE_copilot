from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import EnzymeFamily, EnzymeModule, User, UserRole


def test_core_models_can_create_user_and_family():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(email="demo@example.com", password_hash="hash", role=UserRole.USER)
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Mature microbial transglutaminase",
            description="Mature enzyme engineering target",
        )
        session.add_all([user, family])
        session.commit()

        saved_user = session.scalar(select(User).where(User.email == "demo@example.com"))
        saved_family = session.scalar(select(EnzymeFamily).where(EnzymeFamily.name == family.name))

    assert saved_user is not None
    assert saved_user.role == UserRole.USER
    assert saved_family is not None
    assert saved_family.module == EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE
