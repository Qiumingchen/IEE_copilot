from app.external.enzyme_data import (
    ExternalKineticParameter,
    ExternalMutantRecord,
    ExternalPropertyDatum,
    MockEnzymeDataClient,
    RealEnzymeDataClient,
    _is_relevant_enzyme_article,
    _literature_discovery_queries,
    get_enzyme_data_client,
)


def test_mock_enzyme_data_client_fetches_opt_temperature():
    client = MockEnzymeDataClient()

    records = client.fetch_opt_temperature("microbial transglutaminase")

    assert records == [
        ExternalPropertyDatum(
            property_type="optimal_temperature",
            value_original="55",
            unit_original="degC",
            substrate=None,
            organism="Streptomyces mobaraensis",
            source="enzyme_data_mock",
            evidence="Mock BRENDA-style optimal temperature record",
        )
    ]


def test_mock_enzyme_data_client_fetches_opt_ph_for_anthraquinone_glycosyltransferase():
    client = MockEnzymeDataClient()

    records = client.fetch_opt_pH("anthraquinone glycosyltransferase")

    assert records[0].property_type == "optimal_pH"
    assert records[0].value_original == "7.5"
    assert records[0].organism == "Streptomyces mockensis"


def test_mock_enzyme_data_client_fetches_kinetic_parameters():
    client = MockEnzymeDataClient()

    records = client.fetch_kinetic_parameters("microbial transglutaminase")

    assert records == [
        ExternalKineticParameter(
            substrate="CBZ-Gln-Gly",
            km="2.1",
            kcat="31.0",
            kcat_km=None,
            unit_original="mM; s^-1",
            assay_temperature="45",
            assay_pH="7.0",
            organism="Streptomyces mobaraensis",
            source="enzyme_data_mock",
            evidence="Mock SABIO-RK-style kinetic parameter record",
        )
    ]


def test_mock_enzyme_data_client_fetches_mutants():
    client = MockEnzymeDataClient()

    records = client.fetch_mutants("microbial transglutaminase")

    assert records == [
        ExternalMutantRecord(
            mutation_string="S2P",
            effect_summary="Mock thermostability improvement",
            property_delta={"optimal_temperature_delta_degC": 5},
            substrate=None,
            organism="Streptomyces mobaraensis",
            source="enzyme_data_mock",
            evidence="Mock mutant data record",
        )
    ]


def test_get_enzyme_data_client_returns_replaceable_mock_adapter():
    client = get_enzyme_data_client()

    assert isinstance(client, MockEnzymeDataClient)


def test_real_enzyme_data_client_extracts_property_data_from_europe_pmc(monkeypatch):
    captured_queries = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Characterization of a food enzyme",
                            "abstractText": (
                                "The purified enzyme showed optimum temperature at 72 °C "
                                "and optimum pH 6.5 during starch hydrolysis."
                            ),
                            "journalTitle": "Applied Enzymology",
                            "pubYear": "2025",
                            "doi": "10.1000/real-enzyme",
                            "pmid": "12345678",
                        }
                    ]
                }
            }

    def fake_get(url, params, timeout):
        captured_queries.append((url, params, timeout))
        return Response()

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)

    client = RealEnzymeDataClient(timeout=3)

    temperatures = client.fetch_opt_temperature("alpha amylase")
    ph_values = client.fetch_opt_pH("alpha amylase")

    assert captured_queries[0][0] == "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    query_terms = [params["query"] for _, params, _ in captured_queries if "query" in params]
    assert any("alpha amylase optimum temperature" in query for query in query_terms)
    assert any("alpha amylase optimum pH" in query for query in query_terms)
    assert temperatures == [
        ExternalPropertyDatum(
            property_type="optimal_temperature",
            value_original="72",
            unit_original="degC",
            organism=None,
            source="europepmc",
            evidence=(
                "Applied Enzymology 2025 doi:10.1000/real-enzyme pmid:12345678 | "
                "Evidence quality: literature sentence | "
                "Evidence: The purified enzyme showed optimum temperature at 72 °C and optimum pH 6.5 during starch hydrolysis"
            ),
            reference_title="Characterization of a food enzyme",
            journal="Applied Enzymology",
            year=2025,
            doi="10.1000/real-enzyme",
            pubmed_id="12345678",
        )
    ]
    assert ph_values[0].property_type == "optimal_pH"
    assert ph_values[0].value_original == "6.5"
    assert ph_values[0].source == "europepmc"


def test_real_enzyme_data_client_queries_pubmed_when_europe_pmc_candidates_lack_values(monkeypatch):
    calls = []

    class JsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class TextResponse:
        text = """
        <PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation>
              <PMID>45678999</PMID>
              <Article>
                <Journal>
                  <Title>Journal of Food Enzymes</Title>
                  <JournalIssue><PubDate><Year>2023</Year></PubDate></JournalIssue>
                </Journal>
                <ArticleTitle>Bacillus subtilis amylase characterization</ArticleTitle>
                <Abstract>
                  <AbstractText>The Bacillus subtilis enzyme showed optimum temperature at 64 degC.</AbstractText>
                </Abstract>
              </Article>
            </MedlineCitation>
          </PubmedArticle>
        </PubmedArticleSet>
        """

        def raise_for_status(self):
            return None

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        if "europepmc" in url:
            return JsonResponse(
                {
                    "resultList": {
                        "result": [
                            {
                                "title": f"Amylase purification without assay values {index}",
                                "abstractText": "This study mentions purification but omits optimum conditions.",
                            }
                            for index in range(5)
                        ]
                    }
                }
            )
        if "esearch.fcgi" in url:
            return JsonResponse({"esearchresult": {"idlist": ["45678999"]}})
        if "efetch.fcgi" in url:
            return TextResponse()
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("alpha amylase")

    assert temperatures[0].source == "pubmed"
    assert temperatures[0].value_original == "64"
    assert temperatures[0].organism == "Bacillus subtilis"
    assert any("esearch.fcgi" in url for url, _ in calls)


def test_real_enzyme_data_client_queries_optimal_temperature_synonym(monkeypatch):
    calls = []

    class JsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        if "europepmc" in url and params["query"].endswith(" optimal temperature"):
            return JsonResponse(
                {
                    "resultList": {
                        "result": [
                            {
                                "title": "Optimal temperature of food amylase",
                                "abstractText": (
                                    "The Bacillus subtilis enzyme showed optimal temperature at 68 degC."
                                ),
                                "journalTitle": "Food Enzyme Reports",
                                "pubYear": "2024",
                                "doi": "10.1000/optimal-temperature",
                            }
                        ]
                    }
                }
            )
        if "europepmc" in url:
            return JsonResponse({"resultList": {"result": []}})
        if "esearch.fcgi" in url:
            return JsonResponse({"esearchresult": {"idlist": []}})
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("alpha amylase")

    assert temperatures[0].value_original == "68"
    assert temperatures[0].organism == "Bacillus subtilis"
    query_terms = [params["query"] for url, params in calls if "europepmc" in url]
    assert "alpha amylase optimum temperature" in query_terms
    assert "alpha amylase optimal temperature" in query_terms


def test_real_enzyme_data_client_extracts_organism_and_specific_activity(monkeypatch):
    captured_queries = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Bacillus licheniformis transglutaminase for food processing",
                            "abstractText": (
                                "The purified Bacillus licheniformis enzyme had a specific "
                                "activity of 125 U/mg toward casein."
                            ),
                            "journalTitle": "Food Biocatalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/specific-activity",
                            "pmid": "34567890",
                        }
                    ]
                }
            }

    def fake_get(url, params, timeout):
        captured_queries.append(params["query"])
        return Response()

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("transglutaminase")

    assert "transglutaminase specific activity" in captured_queries[0]
    assert records == [
        ExternalPropertyDatum(
            property_type="specific_activity",
            value_original="125",
            unit_original="U/mg",
            substrate="casein",
            organism="Bacillus licheniformis",
            source="europepmc",
            evidence=(
                "Food Biocatalysis 2024 doi:10.1000/specific-activity pmid:34567890 | "
                "Evidence quality: literature sentence | "
                "Evidence: The purified Bacillus licheniformis enzyme had a specific activity of 125 U/mg toward casein"
            ),
            reference_title="Bacillus licheniformis transglutaminase for food processing",
            journal="Food Biocatalysis",
            year=2024,
            doi="10.1000/specific-activity",
            pubmed_id="34567890",
        )
    ]


def test_real_enzyme_data_client_extracts_specific_activity_unit_variants(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Thermostable food enzyme activity",
                            "abstractText": (
                                "The Bacillus subtilis enzyme reached a specific "
                                "activity of 84 U mg-1 protein toward starch."
                            ),
                            "journalTitle": "Food Catalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/unit-variant",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("food enzyme")

    assert records == [
        ExternalPropertyDatum(
            property_type="specific_activity",
            value_original="84",
            unit_original="U/mg",
            substrate="starch",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Catalysis 2024 doi:10.1000/unit-variant | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme reached a specific activity of 84 U mg-1 protein toward starch"
            ),
            reference_title="Thermostable food enzyme activity",
            journal="Food Catalysis",
            year=2024,
            doi="10.1000/unit-variant",
        )
    ]


def test_real_enzyme_data_client_extracts_specific_activity_unicode_minus_unit(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Amylase activity report",
                            "abstractText": (
                                "The Bacillus subtilis enzyme reached a specific activity "
                                "of 95 U mg\u22121 protein toward soluble starch."
                            ),
                            "journalTitle": "Food Catalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/unicode-minus-unit",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("amylase")

    assert records[0].value_original == "95"
    assert records[0].unit_original == "U/mg"
    assert records[0].substrate == "soluble starch"


def test_real_enzyme_data_client_extracts_value_before_specific_activity(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Amylase activity characterization",
                            "abstractText": (
                                "The Bacillus subtilis enzyme exhibited 210 U/mg "
                                "specific activity toward soluble starch."
                            ),
                            "journalTitle": "Food Catalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/value-before-specific-activity",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("amylase")

    assert records == [
        ExternalPropertyDatum(
            property_type="specific_activity",
            value_original="210",
            unit_original="U/mg",
            substrate="soluble starch",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Catalysis 2024 doi:10.1000/value-before-specific-activity | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme exhibited 210 U/mg specific activity toward soluble starch"
            ),
            reference_title="Amylase activity characterization",
            journal="Food Catalysis",
            year=2024,
            doi="10.1000/value-before-specific-activity",
        )
    ]


def test_real_enzyme_data_client_searches_enzyme_activity_synonym_for_specific_activity(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append(params["query"])
        if params["query"] != "amylase enzyme activity":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Amylase enzyme activity",
                            "abstractText": (
                                "The Bacillus subtilis enzyme displayed enzyme activity "
                                "of 180 U/mg toward soluble starch."
                            ),
                            "journalTitle": "Food Catalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/enzyme-activity-synonym",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("amylase")

    assert "amylase specific activity" in calls
    assert "amylase enzyme activity" in calls
    assert records[0].value_original == "180"
    assert records[0].substrate == "soluble starch"
    assert records[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_extracts_enzyme_activity_was_specific_activity(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Amylase enzyme activity was reported",
                            "abstractText": (
                                "The Bacillus subtilis enzyme activity was 180 U/mg "
                                "toward soluble starch."
                            ),
                            "journalTitle": "Food Catalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/enzyme-activity-was",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("amylase")

    assert records == [
        ExternalPropertyDatum(
            property_type="specific_activity",
            value_original="180",
            unit_original="U/mg",
            substrate="soluble starch",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Catalysis 2024 doi:10.1000/enzyme-activity-was | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme activity was 180 U/mg toward soluble starch"
            ),
            reference_title="Amylase enzyme activity was reported",
            journal="Food Catalysis",
            year=2024,
            doi="10.1000/enzyme-activity-was",
        )
    ]


def test_real_enzyme_data_client_queries_u_mg_minus_one_specific_activity(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append(params["query"])
        if params["query"] != "amylase activity U mg-1":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Amylase U mg-1 activity report",
                            "abstractText": (
                                "The Bacillus subtilis enzyme reached a specific activity "
                                "of 95 U mg-1 protein toward soluble starch."
                            ),
                            "journalTitle": "Food Catalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/u-mg-minus-one-query",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("amylase")

    assert "amylase activity U mg-1" in calls
    assert records[0].value_original == "95"
    assert records[0].substrate == "soluble starch"
    assert records[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_queries_units_per_mg_specific_activity(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append(params["query"])
        if params["query"] != "amylase activity units/mg":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Amylase units per mg activity report",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed a specific activity "
                                "of 118 units/mg protein toward soluble starch."
                            ),
                            "journalTitle": "Food Catalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/units-per-mg-query",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("amylase")

    assert "amylase activity units/mg" in calls
    assert records[0].value_original == "118"
    assert records[0].substrate == "soluble starch"
    assert records[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_extracts_units_per_mg_words_specific_activity(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Amylase units per mg activity report",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed a specific activity "
                                "of 142 units per mg protein toward soluble starch."
                            ),
                            "journalTitle": "Food Catalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/units-per-mg-words",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("amylase")

    assert records == [
        ExternalPropertyDatum(
            property_type="specific_activity",
            value_original="142",
            unit_original="U/mg",
            substrate="soluble starch",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Catalysis 2024 doi:10.1000/units-per-mg-words | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed a specific activity "
                "of 142 units per mg protein toward soluble starch"
            ),
            reference_title="Amylase units per mg activity report",
            journal="Food Catalysis",
            year=2024,
            doi="10.1000/units-per-mg-words",
        )
    ]


def test_real_enzyme_data_client_queries_units_per_ml_activity(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append(params["query"])
        if params["query"] != "amylase activity U/mL":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Amylase volumetric activity report",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed enzyme activity "
                                "of 320 U/mL toward soluble starch."
                            ),
                            "journalTitle": "Food Catalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/u-per-ml-query",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("amylase")

    assert "amylase activity U/mL" in calls
    assert records == [
        ExternalPropertyDatum(
            property_type="activity",
            value_original="320",
            unit_original="U/mL",
            substrate="soluble starch",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Catalysis 2024 doi:10.1000/u-per-ml-query | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed enzyme activity "
                "of 320 U/mL toward soluble starch"
            ),
            reference_title="Amylase volumetric activity report",
            journal="Food Catalysis",
            year=2024,
            doi="10.1000/u-per-ml-query",
        )
    ]


def test_real_enzyme_data_client_extracts_units_per_ml_words_activity(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Amylase volumetric activity words report",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed enzyme activity "
                                "of 410 units per mL toward soluble starch."
                            ),
                            "journalTitle": "Food Catalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/units-per-ml-words",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("amylase")

    assert records == [
        ExternalPropertyDatum(
            property_type="activity",
            value_original="410",
            unit_original="U/mL",
            substrate="soluble starch",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Catalysis 2024 doi:10.1000/units-per-ml-words | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed enzyme activity "
                "of 410 units per mL toward soluble starch"
            ),
            reference_title="Amylase volumetric activity words report",
            journal="Food Catalysis",
            year=2024,
            doi="10.1000/units-per-ml-words",
        )
    ]


def test_real_enzyme_data_client_extracts_international_units_specific_activity(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append(params["query"])
        if params["query"] != "amylase activity IU/mg":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Amylase international unit activity report",
                            "abstractText": (
                                "The Bacillus licheniformis enzyme showed a specific activity "
                                "of 76 IU/mg protein toward soluble starch."
                            ),
                            "journalTitle": "Food Catalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/iu-per-mg-query",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("amylase")

    assert "amylase activity IU/mg" in calls
    assert records[0].value_original == "76"
    assert records[0].unit_original == "U/mg"
    assert records[0].substrate == "soluble starch"
    assert records[0].organism == "Bacillus licheniformis"


def test_real_enzyme_data_client_queries_iu_mg_minus_one_specific_activity(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append(params["query"])
        if params["query"] != "amylase activity IU mg-1":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Amylase IU mg-1 activity report",
                            "abstractText": (
                                "The Bacillus licheniformis enzyme reached a specific activity "
                                "of 82 IU mg-1 protein toward soluble starch."
                            ),
                            "journalTitle": "Food Catalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/iu-mg-minus-one-query",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("amylase")

    assert "amylase activity IU mg-1" in calls
    assert records[0].value_original == "82"
    assert records[0].unit_original == "U/mg"
    assert records[0].substrate == "soluble starch"
    assert records[0].organism == "Bacillus licheniformis"


def test_real_enzyme_data_client_extracts_specific_activity_toward_substrate_was(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Substrate-specific amylase activity",
                            "abstractText": (
                                "The Bacillus subtilis enzyme specific activity toward "
                                "soluble starch was 220 U/mg."
                            ),
                            "journalTitle": "Food Catalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/specific-activity-toward-was",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    records = client.fetch_specific_activity("amylase")

    assert records == [
        ExternalPropertyDatum(
            property_type="specific_activity",
            value_original="220",
            unit_original="U/mg",
            substrate="soluble starch",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Catalysis 2024 doi:10.1000/specific-activity-toward-was | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme specific activity toward soluble starch was 220 U/mg"
            ),
            reference_title="Substrate-specific amylase activity",
            journal="Food Catalysis",
            year=2024,
            doi="10.1000/specific-activity-toward-was",
        )
    ]


def test_real_enzyme_data_client_extracts_common_optimum_ph_temperature_phrasing(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Characterization of microbial transglutaminase",
                            "abstractText": (
                                "The pH and temperature optima were 7.0 and 55 °C, "
                                "respectively. Maximum activity was observed at pH 7.0."
                            ),
                            "journalTitle": "Applied Food Enzymes",
                            "pubYear": "2023",
                            "doi": "10.1000/real-optima",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("microbial transglutaminase")
    ph_values = client.fetch_opt_pH("microbial transglutaminase")

    assert temperatures[0].value_original == "55"
    assert temperatures[0].unit_original == "degC"
    assert ph_values[0].value_original == "7.0"


def test_real_enzyme_data_client_extracts_common_optimum_temperature_ph_phrasing(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Thermostable amylase characterization",
                            "abstractText": (
                                "The optimum temperature and pH were 60 degC and 8.0, "
                                "respectively, for the Bacillus subtilis enzyme."
                            ),
                            "journalTitle": "Applied Food Enzymes",
                            "pubYear": "2024",
                            "doi": "10.1000/temp-ph-order",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("amylase")
    ph_values = client.fetch_opt_pH("amylase")

    assert temperatures[0].value_original == "60"
    assert temperatures[0].organism == "Bacillus subtilis"
    assert ph_values[0].value_original == "8.0"


def test_real_enzyme_data_client_extracts_optimum_ph_temperature_order(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Cellobiose epimerase optimum conditions",
                            "abstractText": (
                                "The optimal pH and temperature were 7.2 and 82 degC, "
                                "respectively, for the Dictyoglomus turgidum enzyme."
                            ),
                            "journalTitle": "Applied Glycoscience",
                            "pubYear": "2014",
                            "doi": "10.1000/ph-temperature-order",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    batch = client.fetch_enzyme_records("cellobiose epimerase Dictyoglomus turgidum", size=3)

    assert [(datum.property_type, datum.value_original) for datum in batch.property_data] == [
        ("optimal_temperature", "82"),
        ("optimal_pH", "7.2"),
    ]


def test_real_enzyme_data_client_extracts_maximum_activity_conditions(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Food enzyme characterization",
                            "abstractText": (
                                "Maximum activity was observed at 60 degC and pH 8.0 "
                                "for the purified Bacillus subtilis enzyme."
                            ),
                            "journalTitle": "Applied Food Enzymes",
                            "pubYear": "2024",
                            "doi": "10.1000/maximum-activity",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")
    ph_values = client.fetch_opt_pH("food enzyme")

    assert temperatures[0].value_original == "60"
    assert temperatures[0].organism == "Bacillus subtilis"
    assert ph_values[0].value_original == "8.0"


def test_real_enzyme_data_client_queries_and_extracts_highest_activity_conditions(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append(params["query"])
        if params["query"] not in {
            "food enzyme highest activity temperature",
            "food enzyme highest activity pH",
        }:
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Food enzyme highest activity",
                            "abstractText": (
                                "The Bacillus subtilis enzyme exhibited highest activity "
                                "at 58 degC and pH 7.5."
                            ),
                            "journalTitle": "Applied Food Enzymes",
                            "pubYear": "2024",
                            "doi": "10.1000/highest-activity",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")
    ph_values = client.fetch_opt_pH("food enzyme")

    assert "food enzyme highest activity temperature" in calls
    assert "food enzyme highest activity pH" in calls
    assert temperatures[0].value_original == "58"
    assert temperatures[0].organism == "Bacillus subtilis"
    assert ph_values[0].value_original == "7.5"


def test_real_enzyme_data_client_extracts_optimum_activity_conditions(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Food enzyme optimum activity",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed optimum activity "
                                "at 55 degC and pH 7.0."
                            ),
                            "journalTitle": "Applied Food Enzymes",
                            "pubYear": "2024",
                            "doi": "10.1000/optimum-activity",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")
    ph_values = client.fetch_opt_pH("food enzyme")

    assert temperatures[0].value_original == "55"
    assert temperatures[0].organism == "Bacillus subtilis"
    assert ph_values[0].value_original == "7.0"
    assert ph_values[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_queries_optimum_activity_for_conditions(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append(params["query"])
        if params["query"] not in {
            "food enzyme optimum activity temperature",
            "food enzyme optimum activity pH",
        }:
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Food enzyme optimum activity query",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed optimum activity "
                                "at 55 degC and pH 7.0."
                            ),
                            "journalTitle": "Applied Food Enzymes",
                            "pubYear": "2024",
                            "doi": "10.1000/optimum-activity-query",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")
    ph_values = client.fetch_opt_pH("food enzyme")

    assert "food enzyme optimum activity temperature" in calls
    assert "food enzyme optimum activity pH" in calls
    assert temperatures[0].value_original == "55"
    assert ph_values[0].value_original == "7.0"


def test_real_enzyme_data_client_extracts_activity_conditions_when_ph_precedes_temperature(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Food enzyme activity conditions",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed maximum activity "
                                "at pH 7.0 and 55 degC."
                            ),
                            "journalTitle": "Applied Food Enzymes",
                            "pubYear": "2024",
                            "doi": "10.1000/ph-before-temperature",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")
    ph_values = client.fetch_opt_pH("food enzyme")

    assert temperatures[0].value_original == "55"
    assert temperatures[0].organism == "Bacillus subtilis"
    assert ph_values[0].value_original == "7.0"


def test_real_enzyme_data_client_extracts_activity_conditions_with_temperature_label(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Food enzyme optimum conditions",
                            "abstractText": (
                                "The Bacillus subtilis enzyme exhibited optimum activity "
                                "under pH 7.5 and temperature 55 degC."
                            ),
                            "journalTitle": "Applied Food Enzymes",
                            "pubYear": "2024",
                            "doi": "10.1000/ph-temperature-label",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")
    ph_values = client.fetch_opt_pH("food enzyme")

    assert temperatures[0].value_original == "55"
    assert ph_values[0].value_original == "7.5"
    assert temperatures[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_extracts_optimum_condition_ranges(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Food enzyme optimum condition ranges",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed optimum temperature "
                                "between 50 and 60 degC and optimum pH between 6.0 and 7.0."
                            ),
                            "journalTitle": "Applied Food Enzymes",
                            "pubYear": "2024",
                            "doi": "10.1000/condition-ranges",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")
    ph_values = client.fetch_opt_pH("food enzyme")

    assert temperatures[0].value_original == "50-60"
    assert temperatures[0].organism == "Bacillus subtilis"
    assert ph_values[0].value_original == "6.0-7.0"
    assert ph_values[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_extracts_hyphenated_optimum_condition_ranges(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Food enzyme hyphenated optimum ranges",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed optimum temperature "
                                "of 50-60 degC and optimum pH of 6.0-7.0."
                            ),
                            "journalTitle": "Applied Food Enzymes",
                            "pubYear": "2024",
                            "doi": "10.1000/hyphenated-condition-ranges",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")
    ph_values = client.fetch_opt_pH("food enzyme")

    assert temperatures[0].value_original == "50-60"
    assert temperatures[0].organism == "Bacillus subtilis"
    assert ph_values[0].value_original == "6.0-7.0"
    assert ph_values[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_extracts_unicode_dash_optimum_condition_ranges(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Food enzyme unicode dash optimum ranges",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed optimum temperature "
                                "of 50\u201360 degC and optimum pH of 6.0\u20137.0."
                            ),
                            "journalTitle": "Applied Food Enzymes",
                            "pubYear": "2024",
                            "doi": "10.1000/unicode-dash-condition-ranges",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")
    ph_values = client.fetch_opt_pH("food enzyme")

    assert temperatures[0].value_original == "50-60"
    assert temperatures[0].organism == "Bacillus subtilis"
    assert ph_values[0].value_original == "6.0-7.0"
    assert ph_values[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_prefers_measurement_sentence_organism(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Bacillus subtilis host background for enzyme production",
                            "abstractText": (
                                "Expression was performed in Bacillus subtilis. "
                                "The Streptomyces mobaraensis enzyme showed optimum temperature at 55 degC."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/measurement-organism",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("microbial transglutaminase")

    assert temperatures[0].organism == "Streptomyces mobaraensis"


def test_real_enzyme_data_client_prefers_abstract_measurement_sentence_over_title(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Bacillus subtilis enzyme candidate active at 55 degC",
                            "abstractText": (
                                "The Aspergillus oryzae enzyme showed optimum temperature at 55 degC."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/title-organism-mismatch",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("amylase")

    assert temperatures[0].organism == "Aspergillus oryzae"
    assert "Evidence: The Aspergillus oryzae enzyme showed optimum temperature" in temperatures[0].evidence


def test_real_enzyme_data_client_resolves_abbreviated_measurement_organism(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Bacillus licheniformis enzyme production background",
                            "abstractText": (
                                "The B. subtilis enzyme showed optimum temperature at 64 degC."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/abbreviated-organism",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("amylase")

    assert temperatures[0].organism == "Bacillus subtilis"
    assert "Evidence: The B. subtilis enzyme showed optimum temperature" in temperatures[0].evidence


def test_real_enzyme_data_client_does_not_fallback_when_abbreviated_organism_is_ambiguous(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Bacillus licheniformis and Brevibacillus laterosporus production hosts",
                            "abstractText": (
                                "The B. subtilis enzyme showed optimum temperature at 64 degC."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/ambiguous-abbreviated-organism",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("amylase")

    assert temperatures[0].organism is None
    assert "Evidence: The B. subtilis enzyme showed optimum temperature" in temperatures[0].evidence


def test_real_enzyme_data_client_does_not_assign_measurement_with_multiple_organisms(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Comparative optimum temperature of food enzymes",
                            "abstractText": (
                                "The Bacillus subtilis and Aspergillus oryzae enzymes showed "
                                "optimum temperature at 55 degC and 45 degC, respectively."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/multiple-organisms",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")

    assert temperatures[0].value_original == "55"
    assert temperatures[0].organism is None


def test_real_enzyme_data_client_splits_comparative_temperature_by_organism(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Comparative optimum temperature of food enzymes",
                            "abstractText": (
                                "The Bacillus subtilis and Aspergillus oryzae enzymes showed "
                                "optimum temperature at 55 degC and 45 degC, respectively."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/comparative-temperatures",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    batch = client.fetch_enzyme_records("food enzyme", size=5)

    assert [(datum.organism, datum.property_type, datum.value_original) for datum in batch.property_data] == [
        ("Bacillus subtilis", "optimal_temperature", "55"),
        ("Aspergillus oryzae", "optimal_temperature", "45"),
    ]


def test_real_enzyme_data_client_splits_whereas_temperature_by_organism(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Contrasting optimal temperatures of food enzymes",
                            "abstractText": (
                                "The Bacillus subtilis enzyme had an optimal temperature of "
                                "55 degC, whereas the Aspergillus oryzae enzyme had an "
                                "optimal temperature of 45 degC."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/whereas-temperatures",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    batch = client.fetch_enzyme_records("food enzyme", size=5)

    assert [
        (datum.organism, datum.property_type, datum.value_original, datum.unit_original)
        for datum in batch.property_data
    ] == [
        ("Bacillus subtilis", "optimal_temperature", "55", "degC"),
        ("Aspergillus oryzae", "optimal_temperature", "45", "degC"),
    ]


def test_real_enzyme_data_client_splits_comparative_ph_by_organism(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Comparative optimum pH of food enzymes",
                            "abstractText": (
                                "The Bacillus subtilis and Aspergillus oryzae enzymes showed "
                                "optimum pH at 7.5 and 6.0, respectively."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/comparative-ph",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    batch = client.fetch_enzyme_records("food enzyme", size=5)

    assert [(datum.organism, datum.property_type, datum.value_original) for datum in batch.property_data] == [
        ("Bacillus subtilis", "optimal_pH", "7.5"),
        ("Aspergillus oryzae", "optimal_pH", "6.0"),
    ]


def test_real_enzyme_data_client_splits_whereas_ph_by_organism(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Contrasting optimal pH of food enzymes",
                            "abstractText": (
                                "The Bacillus subtilis enzyme had an optimal pH of 7.5, "
                                "whereas the Aspergillus oryzae enzyme had an optimal pH of 6.0."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/whereas-ph",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    batch = client.fetch_enzyme_records("food enzyme", size=5)

    assert [(datum.organism, datum.property_type, datum.value_original) for datum in batch.property_data] == [
        ("Bacillus subtilis", "optimal_pH", "7.5"),
        ("Aspergillus oryzae", "optimal_pH", "6.0"),
    ]


def test_real_enzyme_data_client_splits_comparative_specific_activity_by_organism(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Comparative specific activity of food enzymes",
                            "abstractText": (
                                "The Bacillus subtilis and Aspergillus oryzae enzymes showed "
                                "specific activities of 120 U/mg and 85 U/mg toward starch, respectively."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/comparative-specific-activity",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    batch = client.fetch_enzyme_records("food enzyme", size=5)

    assert [(datum.organism, datum.property_type, datum.value_original, datum.substrate) for datum in batch.property_data] == [
        ("Bacillus subtilis", "specific_activity", "120", "starch"),
        ("Aspergillus oryzae", "specific_activity", "85", "starch"),
    ]


def test_real_enzyme_data_client_splits_whereas_specific_activity_by_organism(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Contrasting specific activity of food enzymes",
                            "abstractText": (
                                "The Bacillus subtilis enzyme had a specific activity of "
                                "120 U/mg toward starch, while the Aspergillus oryzae enzyme "
                                "had a specific activity of 85 U/mg toward starch."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/whereas-specific-activity",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    batch = client.fetch_enzyme_records("food enzyme", size=5)

    assert [(datum.organism, datum.property_type, datum.value_original, datum.substrate) for datum in batch.property_data] == [
        ("Bacillus subtilis", "specific_activity", "120", "starch"),
        ("Aspergillus oryzae", "specific_activity", "85", "starch"),
    ]


def test_real_enzyme_data_client_prefers_enzyme_source_over_expression_host(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Recombinant food enzyme characterization",
                            "abstractText": (
                                "The transglutaminase from Streptomyces mobaraensis was expressed "
                                "in Escherichia coli. The recombinant enzyme showed optimum "
                                "temperature at 55 degC."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/source-over-host",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("microbial transglutaminase")

    assert temperatures[0].value_original == "55"
    assert temperatures[0].organism == "Streptomyces mobaraensis"


def test_real_enzyme_data_client_prefers_source_when_measurement_sentence_names_expression_host(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Recombinant transglutaminase optimum temperature",
                            "abstractText": (
                                "The transglutaminase from Streptomyces mobaraensis was cloned. "
                                "The Escherichia coli recombinant enzyme showed "
                                "optimum temperature at 55 degC."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/source-over-host-measurement",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("microbial transglutaminase")

    assert temperatures[0].value_original == "55"
    assert temperatures[0].organism == "Streptomyces mobaraensis"


def test_real_enzyme_data_client_extracts_property_data_from_europe_pmc_full_text(monkeypatch):
    calls = []

    class JsonResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Full text characterization of microbial transglutaminase",
                            "abstractText": "The abstract reports purification but omits activity optima.",
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2021",
                            "doi": "10.1000/full-text-enzyme",
                            "pmid": "76543210",
                            "pmcid": "PMC7654321",
                        }
                    ]
                }
            }

    class XmlResponse:
        text = """
        <article>
          <body>
            <p>The Streptomyces mobaraensis enzyme showed optimum temperature at 55 degC.</p>
          </body>
        </article>
        """

        def raise_for_status(self):
            return None

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        if url.endswith("/fullTextXML"):
            return XmlResponse()
        return JsonResponse()

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("microbial transglutaminase")

    assert any(url.endswith("/PMC7654321/fullTextXML") for url, _ in calls)
    assert temperatures == [
        ExternalPropertyDatum(
            property_type="optimal_temperature",
            value_original="55",
            unit_original="degC",
            organism="Streptomyces mobaraensis",
            source="europepmc",
            evidence=(
                "Food Enzyme Reports 2021 doi:10.1000/full-text-enzyme pmid:76543210 | "
                "Evidence quality: literature sentence | "
                "Evidence: The Streptomyces mobaraensis enzyme showed optimum temperature at 55 degC"
            ),
            reference_title="Full text characterization of microbial transglutaminase",
            journal="Food Enzyme Reports",
            year=2021,
            doi="10.1000/full-text-enzyme",
            pubmed_id="76543210",
        )
    ]


def test_real_enzyme_data_client_reuses_europe_pmc_full_text_between_property_fetches(monkeypatch):
    calls = []

    class JsonResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Full text characterization of microbial transglutaminase",
                            "abstractText": "The abstract reports purification but omits activity optima.",
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2021",
                            "doi": "10.1000/full-text-cache",
                            "pmid": "76543211",
                            "pmcid": "PMC7654324",
                        }
                    ]
                }
            }

    class XmlResponse:
        text = """
        <article>
          <body>
            <p>The Streptomyces mobaraensis enzyme showed optimum temperature at 55 degC.</p>
            <p>The Streptomyces mobaraensis enzyme showed optimum pH at 7.0.</p>
          </body>
        </article>
        """

        def raise_for_status(self):
            return None

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        if url.endswith("/fullTextXML"):
            return XmlResponse()
        return JsonResponse()

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("microbial transglutaminase")
    ph_values = client.fetch_opt_pH("microbial transglutaminase")

    assert temperatures[0].value_original == "55"
    assert ph_values[0].value_original == "7.0"
    assert [url for url, _ in calls if url.endswith("/PMC7654324/fullTextXML")] == [
        "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7654324/fullTextXML"
    ]


def test_real_enzyme_data_client_skips_full_text_when_abstract_has_property_value(monkeypatch):
    calls = []

    class JsonResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Abstract characterization of microbial transglutaminase",
                            "abstractText": (
                                "The Streptomyces mobaraensis enzyme showed optimum temperature at 55 degC."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2021",
                            "doi": "10.1000/abstract-enzyme",
                            "pmid": "76543211",
                            "pmcid": "PMC7654322",
                        }
                    ]
                }
            }

    class XmlResponse:
        text = """
        <article>
          <body>
            <p>The full text repeated optimum temperature at 55 degC.</p>
          </body>
        </article>
        """

        def raise_for_status(self):
            return None

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        if url.endswith("/fullTextXML"):
            return XmlResponse()
        return JsonResponse()

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("microbial transglutaminase")

    assert not any(url.endswith("/PMC7654322/fullTextXML") for url, _ in calls)
    assert temperatures[0].value_original == "55"
    assert temperatures[0].evidence == (
        "Food Enzyme Reports 2021 doi:10.1000/abstract-enzyme pmid:76543211 | "
        "Evidence quality: literature sentence | "
        "Evidence: The Streptomyces mobaraensis enzyme showed optimum temperature at 55 degC"
    )


def test_real_enzyme_data_client_skips_full_text_when_abstract_has_volumetric_activity(monkeypatch):
    calls = []

    class JsonResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Abstract volumetric activity of microbial transglutaminase",
                            "abstractText": (
                                "The Streptomyces mobaraensis enzyme activity was 18 U/mL "
                                "during casein crosslinking."
                            ),
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2021",
                            "doi": "10.1000/abstract-volumetric-activity",
                            "pmid": "76543212",
                            "pmcid": "PMC7654323",
                        }
                    ]
                }
            }

    class XmlResponse:
        text = """
        <article>
          <body>
            <p>The full text repeated enzyme activity was 18 U/mL.</p>
          </body>
        </article>
        """

        def raise_for_status(self):
            return None

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        if url.endswith("/fullTextXML"):
            return XmlResponse()
        return JsonResponse()

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    activities = client.fetch_specific_activity("microbial transglutaminase")

    assert not any(url.endswith("/PMC7654323/fullTextXML") for url, _ in calls)
    assert activities[0].property_type == "activity"
    assert activities[0].value_original == "18"
    assert activities[0].unit_original == "U/mL"
    assert activities[0].organism == "Streptomyces mobaraensis"


def test_real_enzyme_data_client_extracts_kinetics_and_mutants_from_europe_pmc(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Mutation and kinetic analysis of a food enzyme",
                            "abstractText": (
                                "Variant A123V improved thermostability. For maltose, "
                                "Km was 1.8 mM and kcat was 42 s-1 at 45 degC and pH 7.0."
                            ),
                            "journalTitle": "Food Biocatalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/kinetic-mutant",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("amylase")
    mutants = client.fetch_mutants("amylase")

    assert kinetics == [
        ExternalKineticParameter(
            substrate="maltose",
            km="1.8",
            kcat="42",
            kcat_km=None,
            unit_original="mM; s^-1",
            assay_temperature="45",
            assay_pH="7.0",
            organism=None,
            source="europepmc",
            evidence=(
                "Food Biocatalysis 2024 doi:10.1000/kinetic-mutant | "
                "Evidence quality: literature sentence | "
                "Evidence: For maltose, Km was 1.8 mM and kcat was 42 s-1 at 45 degC and pH 7.0"
            ),
            reference_title="Mutation and kinetic analysis of a food enzyme",
            journal="Food Biocatalysis",
            year=2024,
            doi="10.1000/kinetic-mutant",
        )
    ]
    assert mutants == [
        ExternalMutantRecord(
            mutation_string="A123V",
            effect_summary="Real literature mention: Variant A123V improved thermostability.",
            property_delta={},
            substrate=None,
            organism=None,
            source="europepmc",
            evidence=(
                "Food Biocatalysis 2024 doi:10.1000/kinetic-mutant | "
                "Evidence quality: literature sentence | "
                "Evidence: Variant A123V improved thermostability."
            ),
            reference_title="Mutation and kinetic analysis of a food enzyme",
            journal="Food Biocatalysis",
            year=2024,
            doi="10.1000/kinetic-mutant",
        )
    ]


def test_real_enzyme_data_client_extracts_combined_mutation_strings(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Combined mutant characterization",
                            "abstractText": (
                                "The Bacillus subtilis enzyme mutant A123V/S124P improved "
                                "thermostability and retained activity."
                            ),
                            "journalTitle": "Food Biocatalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/combined-mutant",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    mutants = client.fetch_mutants("amylase")

    assert [record.mutation_string for record in mutants] == ["A123V/S124P"]
    assert mutants[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_extracts_plus_separated_combined_mutation_strings(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Plus separated mutant characterization",
                            "abstractText": (
                                "The Bacillus subtilis enzyme mutant A123V+S124P improved "
                                "specific activity."
                            ),
                            "journalTitle": "Food Biocatalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/plus-mutant",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    mutants = client.fetch_mutants("amylase")

    assert [record.mutation_string for record in mutants] == ["A123V+S124P"]


def test_real_enzyme_data_client_searches_site_directed_mutagenesis_for_mutants(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append(params["query"])
        if params["query"] != "amylase site-directed mutagenesis":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Amylase site-directed mutagenesis",
                            "abstractText": (
                                "Site-directed mutagenesis of the Bacillus subtilis enzyme "
                                "generated A123V with improved thermostability."
                            ),
                            "journalTitle": "Food Biocatalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/site-directed-mutagenesis",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    mutants = client.fetch_mutants("amylase")

    assert "amylase site-directed mutagenesis" in calls
    assert [record.mutation_string for record in mutants] == ["A123V"]
    assert mutants[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_searches_engineered_variant_for_mutants(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append(params["query"])
        if params["query"] != "amylase engineered variant":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Engineered amylase variant",
                            "abstractText": (
                                "The engineered variant A123V of Bacillus subtilis amylase "
                                "showed higher activity."
                            ),
                            "journalTitle": "Food Biocatalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/engineered-variant",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    mutants = client.fetch_mutants("amylase")

    assert "amylase engineered variant" in calls
    assert [record.mutation_string for record in mutants] == ["A123V"]
    assert mutants[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_extracts_mutant_specific_activity_fold_change(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Activity-improved enzyme mutant",
                            "abstractText": (
                                "The Bacillus subtilis mutant A123V showed a 2.3-fold higher "
                                "specific activity toward soluble starch."
                            ),
                            "journalTitle": "Food Biocatalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/activity-fold-mutant",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    mutants = client.fetch_mutants("amylase")

    assert mutants[0].mutation_string == "A123V"
    assert mutants[0].property_delta == {"specific_activity_fold_change": 2.3}
    assert mutants[0].substrate == "soluble starch"


def test_real_enzyme_data_client_extracts_decreased_mutant_specific_activity_fold_change(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Activity-reduced enzyme mutant",
                            "abstractText": (
                                "The Bacillus subtilis mutant A123V showed a 2.3-fold lower "
                                "specific activity toward soluble starch."
                            ),
                            "journalTitle": "Food Biocatalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/activity-lower-fold-mutant",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    mutants = client.fetch_mutants("amylase")

    assert mutants[0].mutation_string == "A123V"
    assert mutants[0].property_delta == {"specific_activity_fold_change": -2.3}
    assert mutants[0].substrate == "soluble starch"


def test_real_enzyme_data_client_extracts_mutant_thermostability_fold_change(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Thermostable enzyme mutant",
                            "abstractText": (
                                "The Bacillus subtilis mutant A123V showed 5-fold higher "
                                "thermostability after incubation at 60 degC."
                            ),
                            "journalTitle": "Food Biocatalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/thermostability-fold-mutant",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    mutants = client.fetch_mutants("amylase")

    assert mutants[0].mutation_string == "A123V"
    assert mutants[0].property_delta == {"thermostability_fold_change": 5.0}


def test_real_enzyme_data_client_extracts_decreased_mutant_thermostability_fold_change(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Destabilized enzyme mutant",
                            "abstractText": (
                                "The Bacillus subtilis mutant A123V showed 3-fold reduced "
                                "thermostability after incubation at 60 degC."
                            ),
                            "journalTitle": "Food Biocatalysis",
                            "pubYear": "2024",
                            "doi": "10.1000/reduced-thermostability-mutant",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    mutants = client.fetch_mutants("amylase")

    assert mutants[0].mutation_string == "A123V"
    assert mutants[0].property_delta == {"thermostability_fold_change": -3.0}


def test_real_enzyme_data_client_extracts_kinetics_of_value_for_substrate(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Kinetic characterization of a protease",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed a Km of 0.8 mM "
                                "for casein and a kcat of 12 s-1."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/km-of-casein",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert kinetics == [
        ExternalKineticParameter(
            substrate="casein",
            km="0.8",
            kcat="12",
            kcat_km=None,
            unit_original="mM; s^-1",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Enzyme Kinetics 2024 doi:10.1000/km-of-casein | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed a Km of 0.8 mM for casein and a kcat of 12 s-1"
            ),
            reference_title="Kinetic characterization of a protease",
            journal="Food Enzyme Kinetics",
            year=2024,
            doi="10.1000/km-of-casein",
        )
    ]


def test_real_enzyme_data_client_preserves_km_micromolar_unit(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Protease micromolar Km",
                            "abstractText": (
                                "For casein, the Bacillus subtilis enzyme Km was 250 uM "
                                "at 37 degC and pH 7.5."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/km-micromolar",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert kinetics[0].substrate == "casein"
    assert kinetics[0].km == "250"
    assert kinetics[0].unit_original == "uM"
    assert kinetics[0].assay_temperature == "37"
    assert kinetics[0].assay_pH == "7.5"
    assert kinetics[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_extracts_kinetic_value_labels(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Protease kinetic value labels",
                            "abstractText": (
                                "The Bacillus subtilis enzyme was characterized with casein. "
                                "The Km value was 0.9 mM and the kcat value was 15 s-1."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/kinetic-value-labels",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert kinetics[0].km == "0.9"
    assert kinetics[0].kcat == "15"
    assert kinetics[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_extracts_kinetic_value_labels_for_substrate(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Protease kinetic values",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed Km value for casein "
                                "was 0.9 mM and kcat value was 15 s-1."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/kinetic-value-labels-substrate",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert kinetics[0].substrate == "casein"
    assert kinetics[0].km == "0.9"
    assert kinetics[0].kcat == "15"


def test_real_enzyme_data_client_extracts_joint_km_kcat_values_for_substrate(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Joint kinetic constants of protease",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed Km and kcat values "
                                "for casein were 0.8 mM and 12 s-1, respectively."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/joint-km-kcat",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert kinetics == [
        ExternalKineticParameter(
            substrate="casein",
            km="0.8",
            kcat="12",
            kcat_km=None,
            unit_original="mM; s^-1",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Enzyme Kinetics 2024 doi:10.1000/joint-km-kcat | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed Km and kcat values for casein were 0.8 mM and 12 s-1, respectively"
            ),
            reference_title="Joint kinetic constants of protease",
            journal="Food Enzyme Kinetics",
            year=2024,
            doi="10.1000/joint-km-kcat",
        )
    ]


def test_real_enzyme_data_client_extracts_joint_km_kcat_values_before_substrate(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Joint kinetic constants before substrate",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed Km and kcat were "
                                "0.8 mM and 12 s-1, respectively, for casein."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/joint-km-kcat-before-substrate",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert kinetics == [
        ExternalKineticParameter(
            substrate="casein",
            km="0.8",
            kcat="12",
            kcat_km=None,
            unit_original="mM; s^-1",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Enzyme Kinetics 2024 doi:10.1000/joint-km-kcat-before-substrate | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed Km and kcat were 0.8 mM and 12 s-1, respectively, for casein"
            ),
            reference_title="Joint kinetic constants before substrate",
            journal="Food Enzyme Kinetics",
            year=2024,
            doi="10.1000/joint-km-kcat-before-substrate",
        )
    ]


def test_real_enzyme_data_client_extracts_joint_kcat_km_values_for_substrate(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Reverse order kinetic constants of protease",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed kcat and Km values "
                                "for casein were 12 s-1 and 0.8 mM, respectively."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/joint-kcat-km",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert kinetics == [
        ExternalKineticParameter(
            substrate="casein",
            km="0.8",
            kcat="12",
            kcat_km=None,
            unit_original="mM; s^-1",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Enzyme Kinetics 2024 doi:10.1000/joint-kcat-km | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed kcat and Km values for casein were 12 s-1 and 0.8 mM, respectively"
            ),
            reference_title="Reverse order kinetic constants of protease",
            journal="Food Enzyme Kinetics",
            year=2024,
            doi="10.1000/joint-kcat-km",
        )
    ]


def test_real_enzyme_data_client_extracts_apparent_km_for_substrate(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Apparent kinetic constants of amylase",
                            "abstractText": (
                                "The Bacillus subtilis enzyme had an apparent Km for soluble "
                                "starch of 1.4 mM and a kcat of 22 s-1."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/apparent-km",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("amylase")

    assert kinetics == [
        ExternalKineticParameter(
            substrate="soluble starch",
            km="1.4",
            kcat="22",
            kcat_km=None,
            unit_original="mM; s^-1",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Enzyme Kinetics 2024 doi:10.1000/apparent-km | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme had an apparent Km for soluble starch of 1.4 mM and a kcat of 22 s-1"
            ),
            reference_title="Apparent kinetic constants of amylase",
            journal="Food Enzyme Kinetics",
            year=2024,
            doi="10.1000/apparent-km",
        )
    ]


def test_real_enzyme_data_client_extracts_km_for_substrate_and_kcat(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Kinetic constants with Km substrate phrase",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed Km for casein and "
                                "kcat were 0.8 mM and 12 s-1, respectively."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/km-for-substrate-and-kcat",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert kinetics == [
        ExternalKineticParameter(
            substrate="casein",
            km="0.8",
            kcat="12",
            kcat_km=None,
            unit_original="mM; s^-1",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Enzyme Kinetics 2024 doi:10.1000/km-for-substrate-and-kcat | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed Km for casein and kcat were 0.8 mM and 12 s-1, respectively"
            ),
            reference_title="Kinetic constants with Km substrate phrase",
            journal="Food Enzyme Kinetics",
            year=2024,
            doi="10.1000/km-for-substrate-and-kcat",
        )
    ]


def test_real_enzyme_data_client_extracts_joint_km_kcat_kcat_km_values(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Full kinetic constants with catalytic efficiency",
                            "abstractText": (
                                "For lactose, the Dictyoglomus turgidum enzyme Km, kcat, "
                                "and kcat/Km values were 1.2 mM, 33 s-1, and "
                                "27.5 mM-1 s-1, respectively."
                            ),
                            "journalTitle": "Applied Glycoscience",
                            "pubYear": "2014",
                            "doi": "10.1000/full-kinetic-constants",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("cellobiose 2-epimerase")

    assert kinetics == [
        ExternalKineticParameter(
            substrate="lactose",
            km="1.2",
            kcat="33",
            kcat_km="27.5",
            unit_original="mM; s^-1; mM^-1 s^-1",
            assay_temperature=None,
            assay_pH=None,
            organism="Dictyoglomus turgidum",
            source="europepmc",
            evidence=(
                "Applied Glycoscience 2014 doi:10.1000/full-kinetic-constants | "
                "Evidence quality: literature sentence | "
                "Evidence: For lactose, the Dictyoglomus turgidum enzyme Km, kcat, and kcat/Km values "
                "were 1.2 mM, 33 s-1, and 27.5 mM-1 s-1, respectively"
            ),
            reference_title="Full kinetic constants with catalytic efficiency",
            journal="Applied Glycoscience",
            year=2014,
            doi="10.1000/full-kinetic-constants",
        )
    ]


def test_real_enzyme_data_client_splits_comparative_km_kcat_by_organism(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Comparative kinetic constants of food enzymes",
                            "abstractText": (
                                "The Bacillus subtilis and Aspergillus oryzae enzymes showed "
                                "Km values for starch of 1.2 mM and 0.8 mM, respectively, "
                                "and kcat values of 33 s-1 and 21 s-1, respectively."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/comparative-kinetics",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    batch = client.fetch_enzyme_records("food enzyme", size=5)

    assert [(datum.organism, datum.substrate, datum.km, datum.kcat) for datum in batch.kinetic_parameters] == [
        ("Bacillus subtilis", "starch", "1.2", "33"),
        ("Aspergillus oryzae", "starch", "0.8", "21"),
    ]


def test_real_enzyme_data_client_splits_comparative_kcat_km_by_organism(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Comparative catalytic efficiencies of food enzymes",
                            "abstractText": (
                                "The Bacillus subtilis and Aspergillus oryzae enzymes showed "
                                "kcat/Km values for starch of 27.5 mM-1 s-1 and "
                                "18.2 mM-1 s-1, respectively."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/comparative-kcat-km",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    batch = client.fetch_enzyme_records("food enzyme", size=5)

    assert [
        (datum.organism, datum.substrate, datum.kcat_km, datum.unit_original)
        for datum in batch.kinetic_parameters
    ] == [
        ("Bacillus subtilis", "starch", "27.5", "mM^-1 s^-1"),
        ("Aspergillus oryzae", "starch", "18.2", "mM^-1 s^-1"),
    ]


def test_real_enzyme_data_client_extracts_catalytic_efficiency_for_substrate(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Protease catalytic efficiency",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed a catalytic efficiency "
                                "(kcat/Km) of 5.2 mM-1 s-1 for casein."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/catalytic-efficiency",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert kinetics == [
        ExternalKineticParameter(
            substrate="casein",
            km=None,
            kcat=None,
            kcat_km="5.2",
            unit_original="mM^-1 s^-1",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Enzyme Kinetics 2024 doi:10.1000/catalytic-efficiency | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed a catalytic efficiency (kcat/Km) of 5.2 mM-1 s-1 for casein"
            ),
            reference_title="Protease catalytic efficiency",
            journal="Food Enzyme Kinetics",
            year=2024,
            doi="10.1000/catalytic-efficiency",
        )
    ]


def test_real_enzyme_data_client_extracts_catalytic_efficiency_toward_substrate(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Protease catalytic efficiency toward substrate",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed catalytic efficiency "
                                "toward casein was 7.4 mM-1 s-1."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/catalytic-efficiency-toward",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert kinetics[0].substrate == "casein"
    assert kinetics[0].kcat_km == "7.4"
    assert kinetics[0].unit_original == "mM^-1 s^-1"


def test_real_enzyme_data_client_searches_catalytic_efficiency_synonym_for_kinetics(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        if "sabiork" in url:
            return Response([])
        calls.append(params["query"])
        if params["query"] != "protease catalytic efficiency":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Protease catalytic efficiency",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed catalytic efficiency "
                                "toward casein was 8.6 mM-1 s-1."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/catalytic-efficiency-query",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert "protease Km kcat" in calls
    assert "protease catalytic efficiency" in calls
    assert kinetics[0].substrate == "casein"
    assert kinetics[0].kcat_km == "8.6"
    assert kinetics[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_searches_kcat_km_synonym_for_kinetics(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        if "sabiork" in url:
            return Response([])
        calls.append(params["query"])
        if params["query"] != "protease kcat/Km":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Protease kcat Km report",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed kcat/Km "
                                "of 9.1 mM-1 s-1 for casein."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/kcat-km-query",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert "protease kcat/Km" in calls
    assert kinetics[0].substrate == "casein"
    assert kinetics[0].kcat_km == "9.1"
    assert kinetics[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_preserves_kcat_km_molar_unit(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Protease molar catalytic efficiency",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed kcat/Km "
                                "of 12000 M-1 s-1 for casein."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/kcat-km-molar-unit",
                        }
                    ]
                }
            }

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", lambda *args, **kwargs: Response())
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert kinetics[0].substrate == "casein"
    assert kinetics[0].kcat_km == "12000"
    assert kinetics[0].unit_original == "M^-1 s^-1"
    assert kinetics[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_searches_turnover_number_for_kcat(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        if "sabiork" in url:
            return Response([])
        calls.append(params["query"])
        if params["query"] != "protease turnover number":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Protease turnover number",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed a turnover number "
                                "of 32 s-1 for casein."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/turnover-number-query",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert "protease turnover number" in calls
    assert kinetics[0].substrate == "casein"
    assert kinetics[0].kcat == "32"
    assert kinetics[0].unit_original == "s^-1"
    assert kinetics[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_searches_catalytic_constant_for_kcat(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        if "sabiork" in url:
            return Response([])
        calls.append(params["query"])
        if params["query"] != "protease catalytic constant":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Protease catalytic constant",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed a catalytic constant "
                                "of 18 s-1 for casein at 37 degC and pH 7.5."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/catalytic-constant-query",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert "protease catalytic constant" in calls
    assert kinetics[0].substrate == "casein"
    assert kinetics[0].kcat == "18"
    assert kinetics[0].unit_original == "s^-1"
    assert kinetics[0].assay_temperature == "37"
    assert kinetics[0].assay_pH == "7.5"
    assert kinetics[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_searches_michaelis_constant_for_km(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        if "sabiork" in url:
            return Response([])
        calls.append(params["query"])
        if params["query"] != "protease Michaelis constant":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Protease Michaelis constant",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed a Michaelis constant "
                                "of 0.42 mM for casein at 37 degC and pH 7.5."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/michaelis-constant-query",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert "protease Michaelis constant" in calls
    assert kinetics[0].substrate == "casein"
    assert kinetics[0].km == "0.42"
    assert kinetics[0].unit_original == "mM"
    assert kinetics[0].assay_temperature == "37"
    assert kinetics[0].assay_pH == "7.5"
    assert kinetics[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_searches_michaelis_menten_constant_for_km(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        if "sabiork" in url:
            return Response([])
        calls.append(params["query"])
        if params["query"] != "protease Michaelis-Menten constant":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Protease Michaelis-Menten constant",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed a Michaelis-Menten constant "
                                "of 0.51 mM toward casein at 40 degC and pH 8.0."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/michaelis-menten-constant-query",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert "protease Michaelis-Menten constant" in calls
    assert kinetics[0].substrate == "casein"
    assert kinetics[0].km == "0.51"
    assert kinetics[0].assay_temperature == "40"
    assert kinetics[0].assay_pH == "8.0"
    assert kinetics[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_searches_specificity_constant_for_kcat_km(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        if "sabiork" in url:
            return Response([])
        calls.append(params["query"])
        if params["query"] != "protease specificity constant":
            return Response({"resultList": {"result": []}})
        return Response(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Protease specificity constant",
                            "abstractText": (
                                "The Bacillus subtilis enzyme showed a specificity constant "
                                "of 6.8 mM-1 s-1 for casein."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/specificity-constant-query",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert "protease specificity constant" in calls
    assert kinetics[0].substrate == "casein"
    assert kinetics[0].kcat_km == "6.8"
    assert kinetics[0].unit_original == "mM^-1 s^-1"
    assert kinetics[0].organism == "Bacillus subtilis"


def test_real_enzyme_data_client_extracts_pubmed_abstract_records_when_europe_pmc_has_no_hit(monkeypatch):
    calls = []

    class JsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class TextResponse:
        text = """
        <PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation>
              <PMID>45678901</PMID>
              <Article>
                <Journal>
                  <Title>Journal of Industrial Enzymes</Title>
                  <JournalIssue><PubDate><Year>2022</Year></PubDate></JournalIssue>
                </Journal>
                <ArticleTitle>Bacillus subtilis protease kinetics</ArticleTitle>
                <Abstract>
                  <AbstractText>The Bacillus subtilis enzyme showed toward casein, Km was 0.9 mM and kcat was 81 s-1.</AbstractText>
                </Abstract>
              </Article>
            </MedlineCitation>
          </PubmedArticle>
        </PubmedArticleSet>
        """

        def raise_for_status(self):
            return None

    def fake_get(url, params, timeout):
        calls.append((url, params))
        if "europepmc" in url:
            return JsonResponse({"resultList": {"result": []}})
        if "esearch.fcgi" in url:
            return JsonResponse({"esearchresult": {"idlist": ["45678901"]}})
        if "efetch.fcgi" in url:
            return TextResponse()
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("protease")

    assert any("esearch.fcgi" in url for url, _ in calls)
    assert any("efetch.fcgi" in url for url, _ in calls)
    assert kinetics == [
        ExternalKineticParameter(
            substrate="casein",
            km="0.9",
            kcat="81",
            kcat_km=None,
            unit_original="mM; s^-1",
            organism="Bacillus subtilis",
            source="pubmed",
            evidence=(
                "Journal of Industrial Enzymes 2022 pmid:45678901 | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed toward casein, Km was 0.9 mM and kcat was 81 s-1"
            ),
            reference_title="Bacillus subtilis protease kinetics",
            journal="Journal of Industrial Enzymes",
            year=2022,
            pubmed_id="45678901",
        )
    ]


def test_real_enzyme_data_client_extracts_openalex_records_when_literature_sources_are_sparse(monkeypatch):
    calls = []

    class JsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append((url, params))
        if "europepmc" in url:
            return JsonResponse({"resultList": {"result": []}})
        if "esearch.fcgi" in url:
            return JsonResponse({"esearchresult": {"idlist": []}})
        if "openalex" in url:
            return JsonResponse(
                {
                    "results": [
                        {
                            "display_name": "OpenAlex food enzyme characterization",
                            "abstract_inverted_index": {
                                "The": [0],
                                "Bacillus": [1],
                                "subtilis": [2],
                                "enzyme": [3],
                                "showed": [4],
                                "optimum": [5],
                                "temperature": [6],
                                "at": [7],
                                "62": [8],
                                "degC": [9],
                            },
                            "publication_year": 2024,
                            "doi": "https://doi.org/10.1000/openalex-temperature",
                            "primary_location": {
                                "source": {"display_name": "OpenAlex Food Enzymes"}
                            },
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")

    assert any("openalex" in url for url, _ in calls)
    assert temperatures == [
        ExternalPropertyDatum(
            property_type="optimal_temperature",
            value_original="62",
            unit_original="degC",
            organism="Bacillus subtilis",
            source="openalex",
            evidence=(
                "OpenAlex Food Enzymes 2024 doi:10.1000/openalex-temperature | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed optimum temperature at 62 degC"
            ),
            reference_title="OpenAlex food enzyme characterization",
            journal="OpenAlex Food Enzymes",
            year=2024,
            doi="10.1000/openalex-temperature",
        )
    ]


def test_real_enzyme_data_client_deduplicates_same_doi_across_literature_sources(monkeypatch):
    calls = []

    class JsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append((url, params))
        if "europepmc" in url:
            return JsonResponse(
                {
                    "resultList": {
                        "result": [
                            {
                                "title": "Shared DOI food enzyme characterization",
                                "abstractText": (
                                    "The Bacillus subtilis enzyme showed optimum temperature at 62 degC."
                                ),
                                "journalTitle": "Food Enzyme Reports",
                                "pubYear": "2024",
                                "doi": "https://doi.org/10.1000/shared-temperature",
                            }
                        ]
                    }
                }
            )
        if "esearch.fcgi" in url:
            return JsonResponse({"esearchresult": {"idlist": []}})
        if "openalex" in url:
            return JsonResponse(
                {
                    "results": [
                        {
                            "display_name": "Shared DOI food enzyme characterization",
                            "abstract_inverted_index": {
                                "The": [0],
                                "Bacillus": [1],
                                "subtilis": [2],
                                "enzyme": [3],
                                "showed": [4],
                                "optimum": [5],
                                "temperature": [6],
                                "at": [7],
                                "62": [8],
                                "degC": [9],
                            },
                            "publication_year": 2024,
                            "doi": "10.1000/shared-temperature",
                            "primary_location": {
                                "source": {"display_name": "OpenAlex Food Enzymes"}
                            },
                        }
                    ]
                }
            )
        if "semanticscholar" in url:
            return JsonResponse({"data": []})
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")

    assert any("europepmc" in url for url, _ in calls)
    assert any("openalex" in url for url, _ in calls)
    assert temperatures == [
        ExternalPropertyDatum(
            property_type="optimal_temperature",
            value_original="62",
            unit_original="degC",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Enzyme Reports 2024 doi:10.1000/shared-temperature | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed optimum temperature at 62 degC"
            ),
            reference_title="Shared DOI food enzyme characterization",
            journal="Food Enzyme Reports",
            year=2024,
            doi="10.1000/shared-temperature",
        )
    ]


def test_real_enzyme_data_client_deduplicates_prefixed_doi_across_literature_sources(monkeypatch):
    calls = []

    class JsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append((url, params))
        if "europepmc" in url:
            return JsonResponse(
                {
                    "resultList": {
                        "result": [
                            {
                                "title": "Shared DOI prefix food enzyme characterization",
                                "abstractText": (
                                    "The Bacillus subtilis enzyme showed optimum temperature at 63 degC."
                                ),
                                "journalTitle": "Food Enzyme Reports",
                                "pubYear": "2024",
                                "doi": "doi:10.1000/shared-prefix-temperature",
                            }
                        ]
                    }
                }
            )
        if "esearch.fcgi" in url:
            return JsonResponse({"esearchresult": {"idlist": []}})
        if "openalex" in url:
            return JsonResponse(
                {
                    "results": [
                        {
                            "display_name": "Shared DOI prefix food enzyme characterization",
                            "abstract_inverted_index": {
                                "The": [0],
                                "Bacillus": [1],
                                "subtilis": [2],
                                "enzyme": [3],
                                "showed": [4],
                                "optimum": [5],
                                "temperature": [6],
                                "at": [7],
                                "63": [8],
                                "degC": [9],
                            },
                            "publication_year": 2024,
                            "doi": "10.1000/shared-prefix-temperature",
                            "primary_location": {
                                "source": {"display_name": "OpenAlex Food Enzymes"}
                            },
                        }
                    ]
                }
            )
        if "semanticscholar" in url:
            return JsonResponse({"data": []})
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")

    assert any("europepmc" in url for url, _ in calls)
    assert any("openalex" in url for url, _ in calls)
    assert temperatures == [
        ExternalPropertyDatum(
            property_type="optimal_temperature",
            value_original="63",
            unit_original="degC",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Enzyme Reports 2024 doi:10.1000/shared-prefix-temperature | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed optimum temperature at 63 degC"
            ),
            reference_title="Shared DOI prefix food enzyme characterization",
            journal="Food Enzyme Reports",
            year=2024,
            doi="10.1000/shared-prefix-temperature",
        )
    ]


def test_real_enzyme_data_client_deduplicates_trailing_punctuation_doi_across_literature_sources(monkeypatch):
    calls = []

    class JsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append((url, params))
        if "europepmc" in url:
            return JsonResponse(
                {
                    "resultList": {
                        "result": [
                            {
                                "title": "Shared DOI trailing punctuation food enzyme characterization",
                                "abstractText": (
                                    "The Bacillus subtilis enzyme showed optimum temperature at 64 degC."
                                ),
                                "journalTitle": "Food Enzyme Reports",
                                "pubYear": "2024",
                                "doi": "10.1000/shared-trailing-temperature.",
                            }
                        ]
                    }
                }
            )
        if "esearch.fcgi" in url:
            return JsonResponse({"esearchresult": {"idlist": []}})
        if "openalex" in url:
            return JsonResponse(
                {
                    "results": [
                        {
                            "display_name": "Shared DOI trailing punctuation food enzyme characterization",
                            "abstract_inverted_index": {
                                "The": [0],
                                "Bacillus": [1],
                                "subtilis": [2],
                                "enzyme": [3],
                                "showed": [4],
                                "optimum": [5],
                                "temperature": [6],
                                "at": [7],
                                "64": [8],
                                "degC": [9],
                            },
                            "publication_year": 2024,
                            "doi": "10.1000/shared-trailing-temperature",
                            "primary_location": {
                                "source": {"display_name": "OpenAlex Food Enzymes"}
                            },
                        }
                    ]
                }
            )
        if "semanticscholar" in url:
            return JsonResponse({"data": []})
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")

    assert any("europepmc" in url for url, _ in calls)
    assert any("openalex" in url for url, _ in calls)
    assert temperatures == [
        ExternalPropertyDatum(
            property_type="optimal_temperature",
            value_original="64",
            unit_original="degC",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Enzyme Reports 2024 doi:10.1000/shared-trailing-temperature | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed optimum temperature at 64 degC"
            ),
            reference_title="Shared DOI trailing punctuation food enzyme characterization",
            journal="Food Enzyme Reports",
            year=2024,
            doi="10.1000/shared-trailing-temperature",
        )
    ]


def test_real_enzyme_data_client_skips_secondary_literature_candidates(monkeypatch):
    calls = []

    class JsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append((url, params))
        if "europepmc" in url:
            return JsonResponse(
                {
                    "resultList": {
                        "result": [
                            {
                                "title": "Review of Bacillus subtilis enzyme thermostability",
                                "abstractText": (
                                    "The Bacillus subtilis enzyme showed optimum temperature at 90 degC."
                                ),
                                "journalTitle": "Food Enzyme Reviews",
                                "pubYear": "2024",
                                "doi": "10.1000/review-temperature",
                                "pubType": "Review",
                            }
                        ]
                    }
                }
            )
        if "esearch.fcgi" in url:
            return JsonResponse({"esearchresult": {"idlist": []}})
        if "openalex" in url:
            return JsonResponse(
                {
                    "results": [
                        {
                            "display_name": "Primary Bacillus subtilis enzyme characterization",
                            "abstract_inverted_index": {
                                "The": [0],
                                "Bacillus": [1],
                                "subtilis": [2],
                                "enzyme": [3],
                                "showed": [4],
                                "optimum": [5],
                                "temperature": [6],
                                "at": [7],
                                "62": [8],
                                "degC": [9],
                            },
                            "publication_year": 2024,
                            "doi": "10.1000/primary-temperature",
                            "primary_location": {
                                "source": {"display_name": "OpenAlex Food Enzymes"}
                            },
                        }
                    ]
                }
            )
        if "semanticscholar" in url:
            return JsonResponse({"data": []})
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")

    assert any("europepmc" in url for url, _ in calls)
    assert any("openalex" in url for url, _ in calls)
    assert temperatures == [
        ExternalPropertyDatum(
            property_type="optimal_temperature",
            value_original="62",
            unit_original="degC",
            organism="Bacillus subtilis",
            source="openalex",
            evidence=(
                "OpenAlex Food Enzymes 2024 doi:10.1000/primary-temperature | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed optimum temperature at 62 degC"
            ),
            reference_title="Primary Bacillus subtilis enzyme characterization",
            journal="OpenAlex Food Enzymes",
            year=2024,
            doi="10.1000/primary-temperature",
        )
    ]


def test_real_enzyme_data_client_deduplicates_prefixed_pmid_across_literature_sources(monkeypatch):
    calls = []

    class JsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class TextResponse:
        text = """
        <PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation>
              <PMID>45678901</PMID>
              <Article>
                <Journal>
                  <Title>Food Enzyme Reports</Title>
                  <JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue>
                </Journal>
                <ArticleTitle>Shared PMID food enzyme characterization</ArticleTitle>
                <Abstract>
                  <AbstractText>The Bacillus subtilis enzyme showed optimum temperature at 64 degC.</AbstractText>
                </Abstract>
              </Article>
            </MedlineCitation>
          </PubmedArticle>
        </PubmedArticleSet>
        """

        def raise_for_status(self):
            return None

    def fake_get(url, params, timeout):
        calls.append((url, params))
        if "europepmc" in url:
            return JsonResponse(
                {
                    "resultList": {
                        "result": [
                            {
                                "title": "Shared PMID food enzyme characterization",
                                "abstractText": (
                                    "The Bacillus subtilis enzyme showed optimum temperature at 64 degC."
                                ),
                                "journalTitle": "Food Enzyme Reports",
                                "pubYear": "2024",
                                "pmid": "PMID:45678901",
                            }
                        ]
                    }
                }
            )
        if "esearch.fcgi" in url:
            return JsonResponse({"esearchresult": {"idlist": ["45678901"]}})
        if "efetch.fcgi" in url:
            return TextResponse()
        if "openalex" in url:
            return JsonResponse({"results": []})
        if "semanticscholar" in url:
            return JsonResponse({"data": []})
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    temperatures = client.fetch_opt_temperature("food enzyme")

    assert any("europepmc" in url for url, _ in calls)
    assert any("efetch.fcgi" in url for url, _ in calls)
    assert temperatures == [
        ExternalPropertyDatum(
            property_type="optimal_temperature",
            value_original="64",
            unit_original="degC",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Enzyme Reports 2024 pmid:45678901 | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed optimum temperature at 64 degC"
            ),
            reference_title="Shared PMID food enzyme characterization",
            journal="Food Enzyme Reports",
            year=2024,
            pubmed_id="45678901",
        )
    ]


def test_real_enzyme_data_client_stops_after_extracted_property_budget_is_filled(monkeypatch):
    client = RealEnzymeDataClient()
    calls = []
    europe_pmc_record = {
        "title": "Fast Europe PMC enzyme hit",
        "abstractText": "The Bacillus subtilis enzyme showed optimum temperature at 62 degC.",
        "journalTitle": "Food Enzyme Reports",
        "pubYear": "2024",
        "doi": "10.1000/fast-hit",
        "_source": "europepmc",
    }

    def search_europe_pmc(query: str, size: int = 5):
        calls.append("europepmc")
        return [europe_pmc_record]

    def search_pubmed(query: str, size: int = 5):
        calls.append("pubmed")
        return []

    def search_openalex(query: str, size: int = 5):
        calls.append("openalex")
        return []

    def search_semantic_scholar(query: str, size: int = 5):
        calls.append("semanticscholar")
        return []

    monkeypatch.setattr(client, "_search_europe_pmc", search_europe_pmc)
    monkeypatch.setattr(client, "_search_pubmed", search_pubmed)
    monkeypatch.setattr(client, "_search_openalex", search_openalex)
    monkeypatch.setattr(client, "_search_semantic_scholar", search_semantic_scholar)

    records = client.fetch_opt_temperature("food enzyme", size=1)

    assert records == [
        ExternalPropertyDatum(
            property_type="optimal_temperature",
            value_original="62",
            unit_original="degC",
            organism="Bacillus subtilis",
            source="europepmc",
            evidence=(
                "Food Enzyme Reports 2024 doi:10.1000/fast-hit | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed optimum temperature at 62 degC"
            ),
            reference_title="Fast Europe PMC enzyme hit",
            journal="Food Enzyme Reports",
            year=2024,
            doi="10.1000/fast-hit",
        )
    ]
    assert calls == ["europepmc"]


def test_real_enzyme_data_client_fetches_all_record_types_from_relevant_papers_once(monkeypatch):
    client = RealEnzymeDataClient()
    calls = []
    progress_events = []
    relevant_record = {
        "title": "Characterization of a Bacillus subtilis food enzyme",
        "abstractText": (
            "The Bacillus subtilis enzyme showed optimum temperature at 62 degC and optimum pH at 7.2. "
            "The specific activity was 18 U/mg. For casein, Km was 1.8 mM and kcat was 42 s-1. "
            "Variant A123V improved thermostability."
        ),
        "journalTitle": "Food Enzyme Reports",
        "pubYear": "2024",
        "doi": "10.1000/relevant-hit",
        "_source": "europepmc",
    }
    unrelated_record = {
        "title": "Clinical case report without enzyme characterization",
        "abstractText": "This paper does not discuss industrial biocatalysis.",
        "journalTitle": "Unrelated Reports",
        "pubYear": "2024",
        "doi": "10.1000/unrelated-hit",
        "_source": "pubmed",
    }

    def search_europe_pmc(query: str, size: int = 5):
        calls.append(("europepmc", query))
        return [relevant_record]

    def search_pubmed(query: str, size: int = 5):
        calls.append(("pubmed", query))
        return [unrelated_record]

    def search_openalex(query: str, size: int = 5):
        calls.append(("openalex", query))
        return []

    def search_semantic_scholar(query: str, size: int = 5):
        calls.append(("semanticscholar", query))
        return []

    monkeypatch.setattr(client, "_search_europe_pmc", search_europe_pmc)
    monkeypatch.setattr(client, "_search_pubmed", search_pubmed)
    monkeypatch.setattr(client, "_search_openalex", search_openalex)
    monkeypatch.setattr(client, "_search_semantic_scholar", search_semantic_scholar)

    batch = client.fetch_enzyme_records("Bacillus subtilis food enzyme", size=3, progress_callback=progress_events.append)

    assert calls[:4] == [
        ("europepmc", "Bacillus subtilis food enzyme"),
        ("pubmed", "Bacillus subtilis food enzyme"),
        ("openalex", "Bacillus subtilis food enzyme"),
        ("semanticscholar", "Bacillus subtilis food enzyme"),
    ]
    assert len(calls) <= 40
    assert [record.property_type for record in batch.property_data] == [
        "optimal_temperature",
        "optimal_pH",
        "specific_activity",
    ]
    assert batch.kinetic_parameters[0].km == "1.8"
    assert batch.kinetic_parameters[0].kcat == "42"
    assert batch.mutant_records[0].mutation_string == "A123V"
    assert progress_events[0]["candidate_articles"] == 1
    assert progress_events[0]["candidate_papers"] == [
        {
            "title": "Characterization of a Bacillus subtilis food enzyme",
            "source": "europepmc",
            "year": 2024,
            "doi": "10.1000/relevant-hit",
            "pubmed_id": None,
        }
    ]
    assert progress_events[0]["relevant_articles"] == 0
    assert progress_events[-1]["articles_scanned"] == 1
    assert progress_events[-1]["filtered_articles"] == 0
    assert progress_events[-1]["relevant_articles"] == 1
    assert progress_events[-1]["found_records"] == 5


def test_real_enzyme_data_client_discovers_papers_without_characterization_keyword(monkeypatch):
    client = RealEnzymeDataClient()
    calls = []
    paper = {
        "title": (
            "Expression, crystallization and preliminary X-ray crystallographic analysis of "
            "cellobiose 2-epimerase from Dictyoglomus turgidum DSM 6724"
        ),
        "abstractText": (
            "Cellobiose 2-epimerase from D. turgidum was purified. "
            "The enzyme showed optimum temperature at 80 degC."
        ),
        "journalTitle": "Acta Crystallographica Section F",
        "pubYear": "2013",
        "pmid": "24100573",
        "_source": "europepmc",
    }

    def search_europe_pmc(query: str, size: int = 5):
        calls.append(query)
        return [paper] if query == "Cellobiose 2-epimerase Dictyoglomus turgidum" else []

    monkeypatch.setattr(client, "_search_europe_pmc", search_europe_pmc)
    monkeypatch.setattr(client, "_search_pubmed", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_openalex", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_semantic_scholar", lambda query, size=5: [])

    batch = client.fetch_enzyme_records(
        "Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4",
        size=3,
    )

    assert "Cellobiose 2-epimerase Dictyoglomus turgidum" in calls
    assert batch.property_data[0].value_original == "80"
    assert batch.property_data[0].reference_title == paper["title"]


def test_real_enzyme_data_client_keeps_broad_literature_query_set_small_and_general():
    queries = _literature_discovery_queries("Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4")

    assert queries[:5] == [
        "Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4",
        "Cellobiose 2-epimerase Dictyoglomus turgidum",
        "Cellobiose 2-epimerase from Dictyoglomus turgidum",
        "Dictyoglomus turgidum Cellobiose 2-epimerase",
        "Cellobiose 2-epimerase Dictyoglomus turgidum characterization",
    ]
    assert len(queries) <= 18


def test_literature_discovery_queries_include_common_enzyme_name_aliases():
    queries = _literature_discovery_queries("Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4")

    assert "Cellobiose epimerase from Dictyoglomus turgidum" in queries
    assert "recombinant Cellobiose 2-epimerase from Dictyoglomus turgidum" in queries


def test_literature_discovery_queries_include_common_experimental_title_patterns():
    queries = _literature_discovery_queries("Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4")

    assert "characterization of recombinant Cellobiose 2-epimerase from Dictyoglomus turgidum" in queries
    assert "characterization of a recombinant Cellobiose 2-epimerase from Dictyoglomus turgidum" in queries
    assert "purification of Cellobiose 2-epimerase from Dictyoglomus turgidum" in queries
    assert "crystallographic analysis of Cellobiose 2-epimerase from Dictyoglomus turgidum" in queries


def test_literature_discovery_queries_include_abbreviated_organism_variants():
    queries = _literature_discovery_queries("Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4")

    assert "Cellobiose 2-epimerase from D. turgidum" in queries
    assert "D. turgidum Cellobiose 2-epimerase" in queries


def test_literature_discovery_queries_keep_strain_with_organism_not_enzyme():
    queries = _literature_discovery_queries(
        "Cellobiose 2-epimerase Dictyoglomus turgidum DSM 6724 B8DZK4"
    )

    assert "Cellobiose 2-epimerase Dictyoglomus turgidum DSM 6724" in queries
    assert "Cellobiose 2-epimerase from Dictyoglomus turgidum DSM 6724" in queries
    assert "Dictyoglomus turgidum DSM 6724 Cellobiose 2-epimerase" in queries
    assert "Cellobiose 2-epimerase DSM 6724 from Dictyoglomus turgidum" not in queries


def test_real_enzyme_data_client_discovers_papers_written_as_enzyme_from_species(monkeypatch):
    client = RealEnzymeDataClient()
    calls = []
    paper = {
        "title": "Characterization of cellobiose 2-epimerase from Dictyoglomus turgidum",
        "abstractText": "The enzyme showed optimum pH 7.5 and optimum temperature at 80 degC.",
        "journalTitle": "Applied Microbiology and Biotechnology",
        "pubYear": "2013",
        "doi": "10.1000/dt-ce-characterization",
        "_source": "europepmc",
    }

    def search_europe_pmc(query: str, size: int = 5):
        calls.append(query)
        return [paper] if query == "Cellobiose 2-epimerase from Dictyoglomus turgidum" else []

    monkeypatch.setattr(client, "_search_europe_pmc", search_europe_pmc)
    monkeypatch.setattr(client, "_search_pubmed", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_openalex", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_semantic_scholar", lambda query, size=5: [])

    batch = client.fetch_enzyme_records(
        "Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4",
        size=3,
    )

    assert "Cellobiose 2-epimerase from Dictyoglomus turgidum" in calls
    assert {datum.property_type for datum in batch.property_data} == {"optimal_temperature", "optimal_pH"}
    assert {datum.organism for datum in batch.property_data} == {"Dictyoglomus turgidum"}


def test_real_enzyme_data_client_discovers_recombinant_characterization_title_pattern(monkeypatch):
    client = RealEnzymeDataClient()
    calls = []
    paper = {
        "title": (
            "Characterization of a recombinant cellobiose 2-epimerase from Dictyoglomus turgidum "
            "that epimerizes and isomerizes beta-1,4- and alpha-1,4-gluco-oligosaccharides"
        ),
        "abstractText": "The enzyme showed optimum temperature at 80 degC and optimum pH at 7.5.",
        "journalTitle": "Applied Microbiology and Biotechnology",
        "pubYear": "2012",
        "doi": "10.1007/s00253-012-4002-5",
        "_source": "europepmc",
    }

    def search_europe_pmc(query: str, size: int = 5):
        calls.append(query)
        if query == "characterization of recombinant Cellobiose 2-epimerase from Dictyoglomus turgidum":
            return [paper]
        return []

    monkeypatch.setattr(client, "_search_europe_pmc", search_europe_pmc)
    monkeypatch.setattr(client, "_search_pubmed", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_openalex", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_semantic_scholar", lambda query, size=5: [])

    batch = client.fetch_enzyme_records(
        "Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4",
        size=3,
    )

    assert "characterization of recombinant Cellobiose 2-epimerase from Dictyoglomus turgidum" in calls
    assert [datum.property_type for datum in batch.property_data] == [
        "substrate_reaction_scope",
        "optimal_temperature",
        "optimal_pH",
    ]
    assert batch.property_data[0].value_original == (
        "epimerizes and isomerizes beta-1,4- and alpha-1,4-gluco-oligosaccharides"
    )
    assert batch.property_data[0].organism == "Dictyoglomus turgidum"
    assert batch.literature_references[0].doi == "10.1007/s00253-012-4002-5"


def test_real_enzyme_data_client_extracts_greek_substrate_scope_from_recombinant_title(monkeypatch):
    client = RealEnzymeDataClient()
    paper = {
        "title": (
            "Characterization of a recombinant cellobiose 2-epimerase from Dictyoglomus turgidum "
            "that epimerizes and isomerizes \u03b2-1,4- and \u03b1-1,4-gluco-oligosaccharides"
        ),
        "abstractText": "The recombinant enzyme was expressed and purified.",
        "journalTitle": "Applied Microbiology and Biotechnology",
        "pubYear": "2012",
        "doi": "10.1007/s00253-012-4002-5",
        "_source": "europepmc",
    }

    monkeypatch.setattr(client, "_search_europe_pmc", lambda query, size=5: [paper])
    monkeypatch.setattr(client, "_search_pubmed", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_openalex", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_semantic_scholar", lambda query, size=5: [])

    batch = client.fetch_enzyme_records(
        "Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4",
        size=3,
    )

    assert batch.literature_references[0].organism == "Dictyoglomus turgidum"
    assert batch.property_data[0].property_type == "substrate_reaction_scope"
    assert batch.property_data[0].value_original == (
        "epimerizes and isomerizes beta-1,4- and alpha-1,4-gluco-oligosaccharides"
    )
    assert batch.property_data[0].organism == "Dictyoglomus turgidum"


def test_real_enzyme_data_client_does_not_fetch_full_text_when_title_has_substrate_scope(monkeypatch):
    client = RealEnzymeDataClient()
    paper = {
        "title": (
            "Characterization of a recombinant cellobiose 2-epimerase from Dictyoglomus turgidum "
            "that epimerizes and isomerizes \u03b2-1,4- and \u03b1-1,4-gluco-oligosaccharides"
        ),
        "abstractText": "The recombinant enzyme was expressed and purified.",
        "journalTitle": "Applied Microbiology and Biotechnology",
        "pubYear": "2012",
        "doi": "10.1007/s00253-012-4002-5",
        "_source": "europepmc",
    }

    monkeypatch.setattr(client, "_search_europe_pmc", lambda query, size=5: [paper])
    monkeypatch.setattr(client, "_search_pubmed", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_openalex", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_semantic_scholar", lambda query, size=5: [])
    monkeypatch.setattr(
        client,
        "_with_europe_pmc_full_text",
        lambda item: (_ for _ in ()).throw(AssertionError("title already has extractable data")),
    )

    batch = client.fetch_enzyme_records(
        "Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4",
        size=3,
    )

    assert batch.property_data[0].property_type == "substrate_reaction_scope"


def test_real_enzyme_data_client_does_not_let_noisy_first_query_hide_later_precise_hits(monkeypatch):
    client = RealEnzymeDataClient()
    paper = {
        "title": "Cellobiose 2-epimerase from Dictyoglomus turgidum",
        "abstractText": "The Dictyoglomus turgidum enzyme showed optimum temperature at 80 degC.",
        "journalTitle": "Food Biocatalysis",
        "pubYear": "2013",
        "doi": "10.1000/precise-dt-ce-hit",
        "_source": "europepmc",
    }

    def search_europe_pmc(query: str, size: int = 5):
        if query == "Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4":
            return [
                {
                    "title": f"Unrelated glycoscience case report {index}",
                    "abstractText": "This article discusses clinical nutrition but not the target enzyme.",
                    "doi": f"10.1000/noisy-{index}",
                    "_source": "europepmc",
                }
                for index in range(size)
            ]
        if query == "Cellobiose 2-epimerase from Dictyoglomus turgidum":
            return [paper]
        return []

    monkeypatch.setattr(client, "_search_europe_pmc", search_europe_pmc)
    monkeypatch.setattr(client, "_search_pubmed", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_openalex", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_semantic_scholar", lambda query, size=5: [])

    batch = client.fetch_enzyme_records(
        "Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4",
        size=3,
    )

    assert [datum.value_original for datum in batch.property_data] == ["80"]


def test_real_enzyme_data_client_keeps_searching_precise_queries_after_many_broad_hits(monkeypatch):
    client = RealEnzymeDataClient()
    precise_paper = {
        "title": (
            "Characterization of a recombinant cellobiose 2-epimerase from Dictyoglomus turgidum "
            "that epimerizes and isomerizes beta-1,4- and alpha-1,4-gluco-oligosaccharides"
        ),
        "abstractText": "The enzyme showed optimum temperature at 80 degC.",
        "journalTitle": "Applied Microbiology and Biotechnology",
        "pubYear": "2012",
        "doi": "10.1007/s00253-012-4002-5",
        "_source": "europepmc",
    }
    broad_papers = [
        {
            "title": f"Cellobiose 2-epimerase survey for Dictyoglomus turgidum related enzymes {index}",
            "abstractText": "This article mentions cellobiose 2-epimerase and Dictyoglomus turgidum.",
            "doi": f"10.1000/broad-{index}",
            "_source": "europepmc",
        }
        for index in range(18)
    ]

    def search_europe_pmc(query: str, size: int = 5):
        if query == "Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4":
            return broad_papers[:size]
        if query == "characterization of a recombinant Cellobiose 2-epimerase from Dictyoglomus turgidum":
            return [precise_paper]
        return []

    monkeypatch.setattr(client, "_search_europe_pmc", search_europe_pmc)
    monkeypatch.setattr(client, "_search_pubmed", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_openalex", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_semantic_scholar", lambda query, size=5: [])

    batch = client.fetch_enzyme_records(
        "Cellobiose 2-epimerase Dictyoglomus turgidum B8DZK4",
        size=3,
    )

    assert any(reference.doi == "10.1007/s00253-012-4002-5" for reference in batch.literature_references)
    assert "80" in [datum.value_original for datum in batch.property_data]


def test_real_enzyme_data_client_ranks_precise_species_articles_before_broad_candidates(monkeypatch):
    client = RealEnzymeDataClient()
    precise_paper = {
        "title": "Characterization of recombinant cellobiose 2-epimerase from Dictyoglomus turgidum",
        "abstractText": "The Dictyoglomus turgidum enzyme showed optimum temperature at 80 degC.",
        "journalTitle": "Applied Microbiology and Biotechnology",
        "pubYear": "2012",
        "doi": "10.1000/precise-dt-characterization",
        "_source": "europepmc",
    }

    def search_europe_pmc(query: str, size: int = 5):
        if query == "Cellobiose 2-epimerase Dictyoglomus turgidum":
            return [
                {
                    "title": f"Broad cellobiose epimerase survey {index}",
                    "abstractText": "This survey discusses several carbohydrate epimerases without the target source species.",
                    "doi": f"10.1000/broad-survey-{index}",
                    "_source": "europepmc",
                }
                for index in range(4)
            ] + [precise_paper]
        return []

    monkeypatch.setattr(client, "_search_europe_pmc", search_europe_pmc)
    monkeypatch.setattr(client, "_search_pubmed", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_openalex", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_semantic_scholar", lambda query, size=5: [])

    candidates = list(client._search_relevant_literature("Cellobiose 2-epimerase Dictyoglomus turgidum", size=3))

    assert [candidate.get("doi") for candidate in candidates][:3] == [
        "10.1000/precise-dt-characterization",
        "10.1000/broad-survey-0",
        "10.1000/broad-survey-1",
    ]


def test_real_enzyme_data_client_returns_relevant_literature_even_without_values(monkeypatch):
    client = RealEnzymeDataClient()
    paper = {
        "title": "Structure of cellobiose 2-epimerase from Dictyoglomus turgidum",
        "abstractText": "Cellobiose 2-epimerase from Dictyoglomus turgidum was purified and crystallized.",
        "journalTitle": "Acta Crystallographica Section F",
        "pubYear": "2013",
        "pmid": "24100573",
        "_source": "europepmc",
    }

    monkeypatch.setattr(client, "_search_europe_pmc", lambda query, size=5: [paper])
    monkeypatch.setattr(client, "_search_pubmed", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_openalex", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_semantic_scholar", lambda query, size=5: [])

    batch = client.fetch_enzyme_records("Cellobiose 2-epimerase Dictyoglomus turgidum", size=3)

    assert batch.property_data == []
    assert batch.literature_references[0].organism == "Dictyoglomus turgidum"
    assert batch.literature_references[0].pubmed_id == "24100573"


def test_real_enzyme_data_client_extracts_epimerase_source_organism_despite_expression_host(monkeypatch):
    client = RealEnzymeDataClient()
    paper = {
        "title": (
            "Characterization of a recombinant cellobiose 2-epimerase from Dictyoglomus turgidum "
            "that epimerizes and isomerizes beta-1,4- and alpha-1,4-gluco-oligosaccharides"
        ),
        "abstractText": (
            "The recombinant enzyme was expressed in Escherichia coli and purified. "
            "The enzyme showed optimum temperature at 80 degC."
        ),
        "journalTitle": "Applied Microbiology and Biotechnology",
        "pubYear": "2012",
        "doi": "10.1007/s00253-012-4002-5",
        "_source": "europepmc",
    }

    monkeypatch.setattr(client, "_search_europe_pmc", lambda query, size=5: [paper])
    monkeypatch.setattr(client, "_search_pubmed", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_openalex", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_semantic_scholar", lambda query, size=5: [])

    batch = client.fetch_enzyme_records("Cellobiose 2-epimerase Dictyoglomus turgidum", size=3)

    assert batch.literature_references[0].organism == "Dictyoglomus turgidum"
    temperature = next(record for record in batch.property_data if record.property_type == "optimal_temperature")
    assert temperature.organism == "Dictyoglomus turgidum"
    assert temperature.value_original == "80"


def test_real_enzyme_data_client_extracts_assay_methods_with_literature_values(monkeypatch):
    client = RealEnzymeDataClient()
    paper = {
        "title": "Biochemical characterization of cellobiose 2-epimerase from Dictyoglomus turgidum",
        "abstractText": (
            "Specific activity toward lactose was 125 U/mg at pH 7.5 and 80 degC using the DNS assay. "
            "The Km value for lactose was 1.2 mM and kcat value was 42 s^-1 at 80 degC and pH 7.5, "
            "determined by HPLC."
        ),
        "journalTitle": "Applied Microbiology and Biotechnology",
        "pubYear": "2012",
        "doi": "10.1000/method-rich-ce",
        "pmid": "24100573",
        "_source": "europepmc",
    }

    monkeypatch.setattr(client, "_search_europe_pmc", lambda query, size=5: [paper])
    monkeypatch.setattr(client, "_search_pubmed", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_openalex", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_semantic_scholar", lambda query, size=5: [])

    batch = client.fetch_enzyme_records("Cellobiose 2-epimerase Dictyoglomus turgidum", size=3)

    activity = next(record for record in batch.property_data if record.property_type == "specific_activity")
    kinetic = batch.kinetic_parameters[0]
    assert activity.value_original == "125"
    assert activity.unit_original == "U/mg"
    assert activity.substrate == "lactose"
    assert activity.assay_temperature == "80"
    assert activity.assay_pH == "7.5"
    assert activity.method == "DNS assay"
    assert "Specific activity toward lactose was 125 U/mg at pH 7.5 and 80 degC using the DNS assay" in activity.evidence
    assert activity.doi == "10.1000/method-rich-ce"
    assert activity.pubmed_id == "24100573"
    assert kinetic.substrate == "lactose"
    assert kinetic.km == "1.2"
    assert kinetic.kcat == "42"
    assert kinetic.assay_temperature == "80"
    assert kinetic.assay_pH == "7.5"
    assert kinetic.method == "HPLC"
    assert "determined by HPLC" in kinetic.evidence


def test_real_enzyme_data_client_keeps_more_relevant_literature_than_property_budget(monkeypatch):
    client = RealEnzymeDataClient()
    papers = [
        {
            "title": f"Cellobiose 2-epimerase from Dictyoglomus turgidum study {index}",
            "abstractText": "Cellobiose 2-epimerase from Dictyoglomus turgidum was purified and characterized.",
            "journalTitle": "Food Enzyme Reports",
            "pubYear": "2013",
            "pmid": str(24100570 + index),
            "_source": "europepmc",
        }
        for index in range(18)
    ]

    monkeypatch.setattr(client, "_search_europe_pmc", lambda query, size=5: papers)
    monkeypatch.setattr(client, "_search_pubmed", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_openalex", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_semantic_scholar", lambda query, size=5: [])

    batch = client.fetch_enzyme_records("Cellobiose 2-epimerase Dictyoglomus turgidum", size=3)

    assert [reference.pubmed_id for reference in batch.literature_references] == [
        str(24100570 + index) for index in range(18)
    ]


def test_relevance_filter_accepts_species_abbreviation_in_literature_record():
    record = {
        "title": "Kinetic properties of cellobiose 2-epimerase from D. turgidum",
        "abstractText": "The purified CE catalyzed lactose conversion at high temperature.",
    }

    assert _is_relevant_enzyme_article(record, "Cellobiose 2-epimerase Dictyoglomus turgidum")


def test_real_enzyme_data_client_caps_total_candidate_literature(monkeypatch):
    client = RealEnzymeDataClient()

    def search_europe_pmc(query: str, size: int = 5):
        return [
            {
                "title": f"Cellobiose 2-epimerase candidate {index} {query}",
                "abstractText": "Dictyoglomus turgidum enzyme showed optimum temperature at 80 degC.",
                "doi": f"10.1000/candidate-{query}-{index}",
                "_source": "europepmc",
            }
            for index in range(size)
        ]

    monkeypatch.setattr(client, "_search_europe_pmc", search_europe_pmc)
    monkeypatch.setattr(client, "_search_pubmed", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_openalex", lambda query, size=5: [])
    monkeypatch.setattr(client, "_search_semantic_scholar", lambda query, size=5: [])

    candidates = list(client._search_relevant_literature("Cellobiose 2-epimerase Dictyoglomus turgidum", size=3))

    assert len(candidates) == 18


def test_real_enzyme_data_client_reuses_literature_search_results_for_same_query(monkeypatch):
    calls = []

    class JsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append((url, params["query"]))
        return JsonResponse(
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Cached food enzyme hit",
                            "abstractText": "The Bacillus subtilis enzyme showed optimum temperature at 62 degC.",
                            "journalTitle": "Food Enzyme Reports",
                            "pubYear": "2024",
                            "doi": "10.1000/cached-hit",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    first = client.fetch_opt_temperature("food enzyme", size=1)
    second = client.fetch_opt_temperature("food enzyme", size=1)

    assert first == second
    assert calls == [
        (
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            "food enzyme optimum temperature",
        )
    ]


def test_real_enzyme_data_client_skips_literature_kinetics_when_sabiork_fills_budget(monkeypatch):
    client = RealEnzymeDataClient()
    calls = []
    sabiork_record = ExternalKineticParameter(
        substrate="casein",
        km="0.8",
        kcat="12",
        unit_original="mM; s^-1",
        organism="Bacillus subtilis",
        source="sabiork",
        evidence="SABIO-RK EntryID 12345 pmid:28193333 | Evidence quality: structured kinetic database",
    )

    def fetch_sabiork(query: str, size: int = 5):
        calls.append("sabiork")
        return [sabiork_record]

    def search_europe_pmc(query: str, size: int = 5):
        calls.append("europepmc")
        return []

    def search_pubmed(query: str, size: int = 5):
        calls.append("pubmed")
        return []

    def search_openalex(query: str, size: int = 5):
        calls.append("openalex")
        return []

    def search_semantic_scholar(query: str, size: int = 5):
        calls.append("semanticscholar")
        return []

    monkeypatch.setattr(client, "_fetch_sabiork_kinetic_parameters", fetch_sabiork)
    monkeypatch.setattr(client, "_search_europe_pmc", search_europe_pmc)
    monkeypatch.setattr(client, "_search_pubmed", search_pubmed)
    monkeypatch.setattr(client, "_search_openalex", search_openalex)
    monkeypatch.setattr(client, "_search_semantic_scholar", search_semantic_scholar)

    kinetics = client.fetch_kinetic_parameters("protease", size=1)

    assert kinetics == [sabiork_record]
    assert calls == ["sabiork"]


def test_real_enzyme_data_client_extracts_semantic_scholar_records_when_other_sources_are_sparse(monkeypatch):
    calls = []

    class JsonResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append((url, params))
        if "europepmc" in url:
            return JsonResponse({"resultList": {"result": []}})
        if "esearch.fcgi" in url:
            return JsonResponse({"esearchresult": {"idlist": []}})
        if "openalex" in url:
            return JsonResponse({"results": []})
        if "semanticscholar" in url:
            return JsonResponse(
                {
                    "data": [
                        {
                            "title": "Semantic Scholar food enzyme characterization",
                            "abstract": (
                                "The Bacillus subtilis enzyme showed optimum pH at 7.2 "
                                "during starch hydrolysis."
                            ),
                            "venue": "Semantic Food Enzymes",
                            "year": 2024,
                            "externalIds": {"DOI": "10.1000/semantic-ph"},
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    ph_values = client.fetch_opt_pH("food enzyme")

    assert any("semanticscholar" in url for url, _ in calls)
    assert ph_values == [
        ExternalPropertyDatum(
            property_type="optimal_pH",
            value_original="7.2",
            organism="Bacillus subtilis",
            source="semanticscholar",
            evidence=(
                "Semantic Food Enzymes 2024 doi:10.1000/semantic-ph | "
                "Evidence quality: literature sentence | "
                "Evidence: The Bacillus subtilis enzyme showed optimum pH at 7.2 during starch hydrolysis"
            ),
            reference_title="Semantic Scholar food enzyme characterization",
            journal="Semantic Food Enzymes",
            year=2024,
            doi="10.1000/semantic-ph",
        )
    ]


def test_real_enzyme_data_client_prefers_sabiork_structured_kinetics(monkeypatch):
    calls = []

    class TextResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    def fake_get(url, params, timeout):
        calls.append((url, params))
        if "searchKineticLaws/entryIDs" in url:
            assert params["q"] == 'UniProtKB_AC:"P81453"'
            return TextResponse("12345\n")
        if "kineticlawsExportTsv" in url:
            assert params["kinlawids"] == "12345"
            return TextResponse(
                "\t".join(
                    [
                        "EntryID",
                        "Organism",
                        "UniprotID",
                        "ECNumber",
                        "Parameter",
                        "ParameterValue",
                        "ParameterUnit",
                        "Substrate",
                        "Temperature",
                        "pH",
                        "PubMedID",
                        "Title",
                        "Year",
                    ]
                )
                + "\n"
                + "\t".join(
                    [
                        "12345",
                        "Streptomyces mobaraensis",
                        "P81453",
                        "2.3.2.13",
                        "Km",
                        "2.4",
                        "mM",
                        "CBZ-Gln-Gly",
                        "45",
                        "7.0",
                        "28193333",
                        "Curated kinetic law for microbial transglutaminase",
                        "2020",
                    ]
                )
                + "\n"
                + "\t".join(
                    [
                        "12345",
                        "Streptomyces mobaraensis",
                        "P81453",
                        "2.3.2.13",
                        "kcat",
                        "31",
                        "s^(-1)",
                        "CBZ-Gln-Gly",
                        "45",
                        "7.0",
                        "28193333",
                        "Curated kinetic law for microbial transglutaminase",
                        "2020",
                    ]
                )
            )
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("Protein-glutamine gamma-glutamyltransferase Streptomyces mobaraensis P81453")

    assert any("searchKineticLaws/entryIDs" in url for url, _ in calls)
    assert any("kineticlawsExportTsv" in url for url, _ in calls)
    assert kinetics == [
        ExternalKineticParameter(
            substrate="CBZ-Gln-Gly",
            km="2.4",
            kcat="31",
            kcat_km=None,
            unit_original="Km:mM; kcat:s^(-1)",
            assay_temperature="45",
            assay_pH="7.0",
            organism="Streptomyces mobaraensis",
            source="sabiork",
            evidence="SABIO-RK EntryID 12345 pmid:28193333 | Evidence quality: structured kinetic database",
            reference_title="Curated kinetic law for microbial transglutaminase",
            year=2020,
            pubmed_id="28193333",
        )
    ]


def test_real_enzyme_data_client_normalizes_prefixed_sabiork_pubmed_id(monkeypatch):
    class TextResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    def fake_get(url, params, timeout):
        if "searchKineticLaws/entryIDs" in url:
            return TextResponse("12345\n")
        if "kineticlawsExportTsv" in url:
            return TextResponse(
                "\t".join(
                    [
                        "EntryID",
                        "Organism",
                        "Parameter",
                        "ParameterValue",
                        "ParameterUnit",
                        "Substrate",
                        "PubMedID",
                    ]
                )
                + "\n"
                + "\t".join(
                    [
                        "12345",
                        "Streptomyces mobaraensis",
                        "Km",
                        "2.4",
                        "mM",
                        "CBZ-Gln-Gly",
                        "PMID: 28193333",
                    ]
                )
            )
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters("Protein-glutamine gamma-glutamyltransferase P81453")

    assert len(kinetics) == 1
    assert kinetics[0].pubmed_id == "28193333"
    assert kinetics[0].evidence == (
        "SABIO-RK EntryID 12345 pmid:28193333 | Evidence quality: structured kinetic database"
    )


def test_real_enzyme_data_client_reuses_sabiork_kinetics_for_same_query(monkeypatch):
    calls = []

    class TextResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    def fake_get(url, params, timeout):
        calls.append((url, params))
        if "searchKineticLaws/entryIDs" in url:
            return TextResponse("12345\n")
        if "kineticlawsExportTsv" in url:
            return TextResponse(
                "\t".join(
                    [
                        "EntryID",
                        "Organism",
                        "UniprotID",
                        "ECNumber",
                        "Parameter",
                        "ParameterValue",
                        "ParameterUnit",
                        "Substrate",
                        "Temperature",
                        "pH",
                        "PubMedID",
                        "Title",
                        "Year",
                    ]
                )
                + "\n"
                + "\t".join(
                    [
                        "12345",
                        "Streptomyces mobaraensis",
                        "P81453",
                        "2.3.2.13",
                        "Km",
                        "2.4",
                        "mM",
                        "CBZ-Gln-Gly",
                        "45",
                        "7.0",
                        "28193333",
                        "Curated kinetic law for microbial transglutaminase",
                        "2020",
                    ]
                )
            )
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    first = client.fetch_kinetic_parameters(
        "Protein-glutamine gamma-glutamyltransferase Streptomyces mobaraensis P81453",
        size=1,
    )
    second = client.fetch_kinetic_parameters(
        "Protein-glutamine gamma-glutamyltransferase Streptomyces mobaraensis P81453",
        size=1,
    )

    assert first == second
    assert [url for url, _ in calls if "searchKineticLaws/entryIDs" in url] == [
        "https://sabiork.h-its.org/sabioRestWebServices/searchKineticLaws/entryIDs"
    ]
    assert [url for url, _ in calls if "kineticlawsExportTsv" in url] == [
        "https://sabiork.h-its.org/sabioRestWebServices/kineticlawsExportTsv"
    ]


def test_real_enzyme_data_client_combines_sabiork_and_literature_kinetics(monkeypatch):
    calls = []

    class TextResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    class JsonResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "resultList": {
                    "result": [
                        {
                            "title": "Transglutaminase catalytic efficiency",
                            "abstractText": (
                                "The Streptomyces mobaraensis enzyme showed catalytic efficiency "
                                "toward casein was 6.4 mM-1 s-1."
                            ),
                            "journalTitle": "Food Enzyme Kinetics",
                            "pubYear": "2024",
                            "doi": "10.1000/sabiork-plus-literature",
                        }
                    ]
                }
            }

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        if "searchKineticLaws/entryIDs" in url:
            return TextResponse("12345\n")
        if "kineticlawsExportTsv" in url:
            return TextResponse(
                "\t".join(
                    [
                        "EntryID",
                        "Organism",
                        "UniprotID",
                        "ECNumber",
                        "Parameter",
                        "ParameterValue",
                        "ParameterUnit",
                        "Substrate",
                        "Temperature",
                        "pH",
                        "PubMedID",
                        "Title",
                        "Year",
                    ]
                )
                + "\n"
                + "\t".join(
                    [
                        "12345",
                        "Streptomyces mobaraensis",
                        "P81453",
                        "2.3.2.13",
                        "Km",
                        "2.4",
                        "mM",
                        "CBZ-Gln-Gly",
                        "45",
                        "7.0",
                        "28193333",
                        "Curated kinetic law for microbial transglutaminase",
                        "2020",
                    ]
                )
            )
        if "europepmc" in url:
            return JsonResponse()
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    kinetics = client.fetch_kinetic_parameters(
        "Protein-glutamine gamma-glutamyltransferase Streptomyces mobaraensis P81453",
        size=5,
    )

    assert [record.source for record in kinetics] == ["sabiork", "europepmc"]
    assert kinetics[0].km == "2.4"
    assert kinetics[1].substrate == "casein"
    assert kinetics[1].kcat_km == "6.4"
    assert any("search" in url and "europepmc" in url for url, _ in calls)


def test_get_enzyme_data_client_uses_real_adapter_when_enabled(monkeypatch):
    monkeypatch.setenv("USE_REAL_SCIENCE_PROVIDERS", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        client = get_enzyme_data_client()
        assert isinstance(client, RealEnzymeDataClient)
    finally:
        get_settings.cache_clear()


def test_real_enzyme_data_client_returns_empty_records_when_provider_fails(monkeypatch):
    def fake_get(*args, **kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr("app.external.enzyme_data.httpx.get", fake_get)
    client = RealEnzymeDataClient()

    assert client.fetch_opt_temperature("alpha amylase") == []
    assert client.fetch_opt_pH("alpha amylase") == []
    assert client.fetch_kinetic_parameters("alpha amylase") == []
    assert client.fetch_mutants("alpha amylase") == []
