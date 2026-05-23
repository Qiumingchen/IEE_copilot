import re


def extract_structure_database_identifiers(text: str, *, file_name: str) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    alphafold_id = extract_alphafold_id(file_name)
    if alphafold_id:
        identifiers["alphafold_id"] = alphafold_id

    for line in text.splitlines():
        record = line[0:6].strip().upper()
        if record == "HEADER":
            candidate_id = line[62:67].strip().upper()
            if not candidate_id:
                match = re.search(r"\b[0-9][A-Z0-9]{3}\b", line.upper())
                candidate_id = match.group(0) if match else ""
            if candidate_id:
                identifiers["pdb_id"] = candidate_id
        elif record == "DBREF" and len(line) >= 42:
            database = line[26:32].strip().upper()
            accession = line[33:41].strip()
            if database in {"UNP", "UNIPROT"} and accession:
                identifiers["uniprot_id"] = accession

        if "alphafold_id" not in identifiers:
            line_alphafold_id = extract_alphafold_id(line)
            if line_alphafold_id:
                identifiers["alphafold_id"] = line_alphafold_id

    return identifiers


def extract_alphafold_id(text: str) -> str | None:
    match = re.search(r"\bAF-[A-Z0-9]+-F\d+\b", text.upper())
    return match.group(0) if match else None


def alphafold_identifier_candidates(alphafold_id: str) -> set[str]:
    candidates = {alphafold_id}
    match = re.fullmatch(r"AF-([A-Z0-9]+)-F\d+", alphafold_id.upper())
    if match:
        candidates.add(match.group(1))
    return candidates
