import os
import json
from neo4j import GraphDatabase

# --- Connection setup (same pattern as test_connection.py) ---
URI = os.environ["NEO4J_URI"]
USERNAME = os.environ["NEO4J_USERNAME"]
PASSWORD = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

# List every JSON file you want to load. "extracted_data_paper2.json" is
# EXCLUDED on purpose - it turned out to be mislabeled (contains a second
# extraction of Paper 3, not Paper 2 - see DOI investigation). The real
# Paper 2 (Jantunen et al.) is now correctly captured in
# extracted_data_paper2_jantunen.json below.
JSON_FILES = [
    "extracted_data.json",
    "extracted_data_paper2_jantunen.json",
    "extracted_data_paper3.json",
    "extracted_data_paper4_native.json",
    "extracted_data_paper5_tang.json",
    "extracted_data_paper6.json",
    "extracted_data_paper7.json",
"extracted_data_paper8.json",
]


def load_record(tx, r):
    """
    tx = a "transaction" - a single unit of work sent to the database.
    r  = one record (one Python dict) from your JSON array.

    This function is called once per record. It runs one Cypher query
    that MERGEs the shared nodes and CREATEs the ExtractionRecord,
    mirroring exactly what we did by hand in the console.
    """

    # This MERGE key is your Rule 9 dedup logic, made real, now in its
    # final (as of tonight) form: doi + metal + extractant + pH + stage +
    # reference_metal + source_location + _source_index.
    #
    # History of why each field is here, so this isn't re-litigated later:
    #   - doi/metal/extractant/pH: the original key. Worked for 5 papers.
    #   - stage_number: Paper 6 differentiates experiments by stage, not
    #     always by pH.
    #   - reference_metal: Rule 8 separation-factor records share every
    #     other field except this one.
    #   - source_location: some Paper 6 figures report multiple points
    #     (a %E-vs-something curve) where pH/stage/reference_metal are
    #     ALL "N.R." for every point - source_location ("Figure 9" etc)
    #     is the one field the pipeline reliably fills differently.
    #   - _source_index: a small number of Paper 6 records (see below)
    #     have EVERY existing schema field identical or "N.R." even
    #     including source_location - e.g. 7 distinct data points all
    #     labelled "Figure 9" with no further distinguishing detail
    #     captured. This is a genuine schema coverage gap (the paper is
    #     plotting against a variable - possibly a continuous stage
    #     count, contact time, or something else - that isn't one of the
    #     22 tracked fields). _source_index is a synthetic, honestly-named
    #     tiebreaker (each record's position in its source JSON array) -
    #     it preserves these records as distinct rather than silently
    #     losing them, but it does NOT represent real chemistry data.
    #     Flag this to Dr. Zhang as a known limitation: these specific
    #     records are distinguishable in the graph, but WHY they differ
    #     is not yet captured and would need the source PDF's figure
    #     captions checked directly to resolve properly.
    #
    # Every other field is set with SET, which works whether the record
    # is newly created or found - so a second, more complete version of
    # the same experiment can fill in details the first pass left as
    # "N.R."
    query = """
    MERGE (metal:Metal {name: $target_metal})
    MERGE (extractant:Extractant {name: $extractant})
    MERGE (diluent:Diluent {name: $diluent})
    MERGE (paper:Paper {doi: $source_doi})

    MERGE (record:ExtractionRecord {
        source_doi: $source_doi,
        target_metal: $target_metal,
        extractant: $extractant,
        initial_pH: $initial_pH,
        stage_number: $stage_number,
        reference_metal: $reference_metal,
        source_location: $source_location,
        _source_index: $_source_index
    })
    SET record.source_location = $source_location,
        record.extractant_concentration = $extractant_concentration,
        record.modifier = $modifier,
        record.equilibrium_pH = $equilibrium_pH,
        record.phase_ratio_OA = $phase_ratio_OA,
        record.initial_metal_concentration = $initial_metal_concentration,
        record.aqueous_concentration_after = $aqueous_concentration_after,
        record.organic_concentration_extract = $organic_concentration_extract,
        record.temperature_C = $temperature_C,
        record.contact_time_min = $contact_time_min,
        record.settling_time_min = $settling_time_min,
        record.stage_number = $stage_number,
        record.extraction_efficiency_pctE = $extraction_efficiency_pctE,
        record.distribution_ratio_D = $distribution_ratio_D,
        record.analytical_method = $analytical_method

    MERGE (record)-[:TARGETS]->(metal)
    MERGE (record)-[:USES_EXTRACTANT]->(extractant)
    MERGE (record)-[:USES_DILUENT]->(diluent)
    MERGE (record)-[:FROM_PAPER]->(paper)
    """

    # This dict maps each $placeholder in the query above to the actual
    # value from this record. .get(key, "N.R.") means: if the JSON is
    # somehow missing a field entirely, fall back to "N.R." rather than
    # crashing - matches your existing anti-hallucination convention.
    # _source_index is set explicitly below (not via .get), since it's
    # injected by main() rather than present in the original JSON.
    params = {k: r.get(k, "N.R.") for k in [
        "source_doi", "source_location", "target_metal", "extractant",
        "extractant_concentration", "diluent", "modifier", "initial_pH",
        "equilibrium_pH", "phase_ratio_OA", "initial_metal_concentration",
        "aqueous_concentration_after", "organic_concentration_extract",
        "temperature_C", "contact_time_min", "settling_time_min",
        "stage_number", "extraction_efficiency_pctE",
        "distribution_ratio_D", "analytical_method", "reference_metal"
    ]}
    params["_source_index"] = r["_source_index"]

    tx.run(query, **params)

    # --- Separation-factor branch ---
    # Rule 8 records have a reference_metal and a separation_factor_beta.
    # These need one extra relationship: the record ALSO compares against
    # a second Metal node (not the same as target_metal).
    #
    # IMPORTANT: this MATCH must use the SAME full key as the MERGE above
    # (including stage_number, reference_metal, source_location, and
    # _source_index). If it used a narrower key, it could match multiple
    # ExtractionRecord nodes at once when several separation-factor
    # records share those fields but differ elsewhere - and silently
    # write the COMPARED_AGAINST relationship onto all of them,
    # cross-contaminating separation factor data between unrelated
    # records.
    if r.get("reference_metal", "N.R.") != "N.R.":
        tx.run("""
            MATCH (record:ExtractionRecord {
                source_doi: $source_doi,
                target_metal: $target_metal,
                extractant: $extractant,
                initial_pH: $initial_pH,
                stage_number: $stage_number,
                reference_metal: $reference_metal,
                source_location: $source_location,
                _source_index: $_source_index
            })
            MERGE (ref_metal:Metal {name: $reference_metal})
            MERGE (record)-[rel:COMPARED_AGAINST]->(ref_metal)
            SET rel.separation_factor_beta = $separation_factor_beta,
                rel.separation_factor_scale = $separation_factor_scale
            """,
            source_doi=r.get("source_doi", "N.R."),
            target_metal=r.get("target_metal", "N.R."),
            extractant=r.get("extractant", "N.R."),
            initial_pH=r.get("initial_pH", "N.R."),
            stage_number=r.get("stage_number", "N.R."),
            reference_metal=r["reference_metal"],
            source_location=r.get("source_location", "N.R."),
            _source_index=r["_source_index"],
            separation_factor_beta=r.get("separation_factor_beta", "N.R."),
            separation_factor_scale=r.get("separation_factor_scale", "N.R."),
        )


def main():
    total_loaded = 0
    with driver.session() as session:
        for filename in JSON_FILES:
            with open(filename, "r") as f:
                records = json.load(f)

            print(f"Loading {len(records)} records from {filename}...")

            # enumerate() gives each record its position in this file's
            # list (0, 1, 2, ...) - this becomes _source_index, the
            # last-resort uniqueness tiebreaker described above. It is
            # scoped per-file, which is fine: the MERGE key already
            # includes source_doi, so index 0 in Paper 1 and index 0 in
            # Paper 6 can never collide with each other.
            for idx, r in enumerate(records):
                r["_source_index"] = idx
                # session.execute_write wraps load_record in a transaction:
                # if anything fails partway through, the whole thing rolls
                # back rather than leaving a half-written record in the graph.
                session.execute_write(load_record, r)
                total_loaded += 1

    print(f"\nDone. {total_loaded} records processed.")
    driver.close()


if __name__ == "__main__":
    main()