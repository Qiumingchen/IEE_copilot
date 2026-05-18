from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    EnzymeEntry,
    EnzymeFamily,
    EnzymeModule,
    ExperimentCondition,
    ExpressionRecord,
    KineticRecord,
    LigandEntry,
    LiteratureReference,
    Project,
    PropertyRecord,
    StructureEntry,
    SubstrateEntry,
    User,
    UserExperiment,
    UserRole,
)


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


def test_epic_one_structure_ligand_and_substrate_models_capture_uploaded_context():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(email="owner@example.com", password_hash="hash", role=UserRole.USER)
        family = EnzymeFamily(
            module=EnzymeModule.ANTHRAQUINONE_GLYCOSYLTRANSFERASE,
            name="Anthraquinone glycosyltransferase",
        )
        session.add_all([user, family])
        session.flush()

        project = Project(owner_user_id=user.id, name="AQ GT engineering")
        enzyme = EnzymeEntry(
            family_id=family.id,
            name="UGT73 example",
            organism="Streptomyces sp.",
            source="local",
        )
        session.add_all([project, enzyme])
        session.flush()

        experiment = UserExperiment(
            project_id=project.id,
            enzyme_entry_id=enzyme.id,
            variant_name="WT",
            measured_property="specific_activity",
            measured_value="12.4",
            unit="U/mg",
            created_by=user.id,
        )
        structure = StructureEntry(
            enzyme_entry_id=enzyme.id,
            structure_type="uploaded_pdb",
            complex_state="enzyme_substrate_complex",
            ligand_summary={"ligands": ["AQ1"]},
            source="user_upload",
        )
        session.add_all([experiment, structure])
        session.flush()

        ligand = LigandEntry(
            structure_entry_id=structure.id,
            ligand_name="anthraquinone substrate 1",
            ligand_code="AQ1",
            ligand_type="substrate",
            chain_id="A",
            residue_number="501",
            smiles="O=C1C=CC2=CC=CC=C2C1=O",
        )
        substrate = SubstrateEntry(
            enzyme_family_id=family.id,
            enzyme_entry_id=enzyme.id,
            user_experiment_id=experiment.id,
            name="anthraquinone substrate 1",
            substrate_class="anthraquinone",
            smiles="O=C1C=CC2=CC=CC=C2C1=O",
        )
        session.add_all([ligand, substrate])
        structure_id = structure.id
        family_id = family.id
        experiment_id = experiment.id
        substrate_name = substrate.name
        session.commit()

        saved_ligand = session.scalar(select(LigandEntry).where(LigandEntry.ligand_code == "AQ1"))
        saved_substrate = session.scalar(select(SubstrateEntry).where(SubstrateEntry.name == substrate_name))

    assert saved_ligand is not None
    assert saved_ligand.structure_entry_id == structure_id
    assert saved_ligand.ligand_type == "substrate"
    assert saved_substrate is not None
    assert saved_substrate.enzyme_family_id == family_id
    assert saved_substrate.user_experiment_id == experiment_id


def test_epic_one_property_kinetic_and_expression_records_can_share_experiment_conditions():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        family = EnzymeFamily(
            module=EnzymeModule.MICROBIAL_TRANSGLUTAMINASE_MATURE,
            name="Mature microbial transglutaminase",
        )
        session.add(family)
        session.flush()

        enzyme = EnzymeEntry(
            family_id=family.id,
            name="mTGase example",
            organism="Streptomyces mobaraensis",
            source="local",
        )
        reference = LiteratureReference(
            title="Thermostability and activity of mature microbial transglutaminase",
            year=2024,
            doi="10.0000/example",
        )
        session.add_all([enzyme, reference])
        session.flush()

        substrate = SubstrateEntry(
            enzyme_family_id=family.id,
            enzyme_entry_id=enzyme.id,
            name="CBZ-Gln-Gly",
            substrate_class="transglutaminase acceptor/donor pair",
        )
        session.add(substrate)
        session.flush()

        condition = ExperimentCondition(
            enzyme_entry_id=enzyme.id,
            substrate_entry_id=substrate.id,
            assay_temperature="45",
            assay_pH="7.0",
            buffer="Tris-HCl",
            method="hydroxamate assay",
            reference_id=reference.id,
        )
        session.add(condition)
        session.flush()

        property_record = PropertyRecord(
            enzyme_entry_id=enzyme.id,
            property_type="optimal_temperature",
            value_original="55",
            unit_original="degC",
            substrate=substrate.name,
            assay_temperature=condition.assay_temperature,
            assay_pH=condition.assay_pH,
            reference_id=reference.id,
        )
        kinetic_record = KineticRecord(
            enzyme_entry_id=enzyme.id,
            substrate=substrate.name,
            km="2.1",
            kcat="31.0",
            unit_original="mM; s^-1",
            assay_temperature=condition.assay_temperature,
            assay_pH=condition.assay_pH,
            reference_id=reference.id,
        )
        expression_record = ExpressionRecord(
            enzyme_entry_id=enzyme.id,
            expression_host="E. coli BL21(DE3)",
            vector="pET-28a",
            expression_level_original="48",
            expression_level_standardized="48",
            soluble_expression="high",
            unit_original="mg/L",
            unit_standardized="mg/L",
            condition_id=condition.id,
            reference_id=reference.id,
        )
        session.add_all([property_record, kinetic_record, expression_record])
        reference_id = reference.id
        condition_id = condition.id
        substrate_id = substrate.id
        session.commit()

        saved_condition = session.scalar(
            select(ExperimentCondition).where(ExperimentCondition.substrate_entry_id == substrate_id)
        )
        saved_expression = session.scalar(
            select(ExpressionRecord).where(ExpressionRecord.expression_host == "E. coli BL21(DE3)")
        )

    assert saved_condition is not None
    assert saved_condition.reference_id == reference_id
    assert saved_expression is not None
    assert saved_expression.condition_id == condition_id
    assert saved_expression.soluble_expression == "high"
