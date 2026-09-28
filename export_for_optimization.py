import os
import csv
from collections import defaultdict
from neo4j import GraphDatabase

URI = os.environ["NEO4J_URI"]
USERNAME = os.environ["NEO4J_USERNAME"]
PASSWORD = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

# Pull every raw ExtractionRecord with a reported D or %E, plus its waste
# source via the existing FROM_PAPER -> SOURCED_FROM chain. OPTIONAL MATCH
# is used for the waste source specifically, since not every paper is
# guaranteed to have one tagged - this way a missing WasteSource doesn't
# silently drop the whole record, it just comes back as null.
QUERY = """
MATCH (r:ExtractionRecord)-[:TARGETS]->(m:Metal),
      (r)-[:USES_EXTRACTANT]->(e:Extractant),
      (r)-[:USES_DILUENT]->(d:Diluent)
OPTIONAL MATCH (r)-[:FROM_PAPER]->(p:Paper)-[:SOURCED_FROM]->(w:WasteSource)
WHERE r.distribution_ratio_D <> "N.R." OR r.extraction_efficiency_pctE <> "N.R."
RETURN m.name AS metal,
       e.name AS extractant,
       e.extractant_family AS extractant_family,
       r.source_doi AS source_doi,
       r.source_location AS source_location,
       r.extractant_concentration AS extractant_concentration,
       d.name AS diluent,
       r.modifier AS modifier,
       r.initial_pH AS initial_pH,
       r.equilibrium_pH AS equilibrium_pH,
       r.phase_ratio_OA AS phase_ratio_OA,
       r.temperature_C AS temperature_C,
       r.contact_time_min AS contact_time_min,
       r.initial_metal_concentration AS initial_metal_concentration,
       r.distribution_ratio_D AS distribution_ratio_D,
       r.extraction_efficiency_pctE AS extraction_efficiency_pctE,
       w.name AS waste_source,
       w.cathode_chemistry AS cathode_chemistry,
       w.is_synthetic AS is_synthetic
"""


def to_float_or_none(value):
    if value is None or value == "N.R.":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def pick_best_record(records):
    with_D = [r for r in records if to_float_or_none(r["distribution_ratio_D"]) is not None]
    if with_D:
        return max(with_D, key=lambda r: to_float_or_none(r["distribution_ratio_D"]))

    with_pctE = [r for r in records if to_float_or_none(r["extraction_efficiency_pctE"]) is not None]
    if with_pctE:
        return max(with_pctE, key=lambda r: to_float_or_none(r["extraction_efficiency_pctE"]))

    return None


def main():
    with driver.session() as session:
        rows = session.run(QUERY).data()

    print(f"Pulled {len(rows)} raw records with reported performance data.")

    groups = defaultdict(list)
    for r in rows:
        groups[(r["metal"], r["extractant"])].append(r)

    output_rows = []
    for (metal, extractant), records in groups.items():
        pH_values = [to_float_or_none(r["initial_pH"]) for r in records]
        pH_values = [v for v in pH_values if v is not None]

        feed_concs = sorted(set(
            r["initial_metal_concentration"] for r in records
            if r["initial_metal_concentration"] != "N.R."
        ))

        best = pick_best_record(records)
        if best is None:
            continue

        output_rows.append({
            "metal": metal,
            "extractant": extractant,
            "extractant_family": best["extractant_family"] or "",
            "pH_range_min": min(pH_values) if pH_values else "N.R.",
            "pH_range_max": max(pH_values) if pH_values else "N.R.",
            "tested_feed_concentrations": "; ".join(feed_concs) if feed_concs else "none reported",
            "waste_source": best["waste_source"] or "unspecified",
            "cathode_chemistry": best["cathode_chemistry"] or "unspecified",
            "is_synthetic": best["is_synthetic"] if best["is_synthetic"] is not None else "unspecified",
            "best_source_doi": best["source_doi"],
            "best_source_location": best["source_location"],
            "best_extractant_concentration": best["extractant_concentration"],
            "best_diluent": best["diluent"],
            "best_modifier": best["modifier"],
            "best_initial_pH": best["initial_pH"],
            "best_equilibrium_pH": best["equilibrium_pH"],
            "best_phase_ratio_OA": best["phase_ratio_OA"],
            "best_temperature_C": best["temperature_C"],
            "best_contact_time_min": best["contact_time_min"],
            "best_distribution_ratio_D": best["distribution_ratio_D"],
            "best_extraction_efficiency_pctE": best["extraction_efficiency_pctE"],
        })

    output_rows.sort(key=lambda row: (row["metal"], row["extractant"]))

    fieldnames = list(output_rows[0].keys())
    with open("optimization_search_space.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Wrote {len(output_rows)} candidate systems to optimization_search_space.csv")
    driver.close()


if __name__ == "__main__":
    main()