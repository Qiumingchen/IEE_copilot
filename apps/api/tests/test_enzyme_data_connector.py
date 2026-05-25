from app.external.enzyme_data import (
    ExternalKineticParameter,
    ExternalMutantRecord,
    ExternalPropertyDatum,
    MockEnzymeDataClient,
    RealEnzymeDataClient,
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
