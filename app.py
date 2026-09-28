import os
import streamlit as st
from neo4j import GraphDatabase

URI = os.environ["NEO4J_URI"]
USERNAME = os.environ["NEO4J_USERNAME"]
PASSWORD = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

st.set_page_config(page_title="LLE Recommender", layout="centered")
st.title("Liquid-Liquid Extraction System Recommender")
st.write(
    "Enter the metal concentrations in your waste stream below. This tool "
    "searches the literature-derived knowledge graph and recommends "
    "extraction systems, showing the tested pH range, the best-performing "
    "reported condition, and how your input compares to what's been tested."
)

st.subheader("Waste stream composition")
col1, col2 = st.columns(2)

with col1:
    co_conc = st.number_input("Co concentration (g/L)", min_value=0.0, value=0.0, step=0.1)
    ni_conc = st.number_input("Ni concentration (g/L)", min_value=0.0, value=0.0, step=0.1)
    mn_conc = st.number_input("Mn concentration (g/L)", min_value=0.0, value=0.0, step=0.1)

with col2:
    li_conc = st.number_input("Li concentration (g/L)", min_value=0.0, value=0.0, step=0.1)
    cu_conc = st.number_input("Cu concentration (g/L)", min_value=0.0, value=0.0, step=0.1)

metal_inputs = {"Co": co_conc, "Ni": ni_conc, "Mn": mn_conc, "Li": li_conc, "Cu": cu_conc}
selected_metals = [metal for metal, conc in metal_inputs.items() if conc > 0]


def get_recommendations(metals):
    # NOTE ON CLAUSE ORDER: the WHERE must sit directly under the MATCH,
    # not under the OPTIONAL MATCH. In Cypher, WHERE attaches to the clause
    # immediately above it. Previously it sat under the OPTIONAL MATCH,
    # where it only decided whether to look up a waste source - it did not
    # filter the records themselves. Result: every record with performance
    # data was returned regardless of which metals the user entered, and
    # the "N.R." baseline records were not excluded either.
    query = """
    MATCH (r:ExtractionRecord)-[:TARGETS]->(m:Metal),
          (r)-[:USES_EXTRACTANT]->(e:Extractant)
    WHERE m.name IN $metals
      AND (r.distribution_ratio_D <> "N.R." OR r.extraction_efficiency_pctE <> "N.R.")
    OPTIONAL MATCH (r)-[:FROM_PAPER]->(p:Paper)-[:SOURCED_FROM]->(w:WasteSource)
    WITH m, e,
         min(toFloat(CASE WHEN r.initial_pH <> "N.R." THEN r.initial_pH END)) AS pH_min,
         max(toFloat(CASE WHEN r.initial_pH <> "N.R." THEN r.initial_pH END)) AS pH_max,
         max(toFloat(CASE WHEN r.distribution_ratio_D <> "N.R." THEN r.distribution_ratio_D END)) AS best_D,
         max(toFloat(CASE WHEN r.extraction_efficiency_pctE <> "N.R." THEN r.extraction_efficiency_pctE END)) AS best_pctE,
         collect(DISTINCT r.initial_metal_concentration) AS tested_feed_concs,
         collect(DISTINCT w.name) AS waste_sources
    RETURN m.name AS metal, e.name AS extractant, pH_min, pH_max,
           best_D, best_pctE, tested_feed_concs, waste_sources
    ORDER BY metal, extractant
    """
    with driver.session() as session:
        result = session.run(query, metals=metals)
        return result.data()


if st.button("Find recommended extraction systems"):
    if not selected_metals:
        st.warning("Enter a concentration greater than 0 for at least one metal.")
    else:
        st.write(f"Searching for: {', '.join(selected_metals)}")
        results = get_recommendations(selected_metals)

        if not results:
            st.error("No matching extraction data found in the current literature set.")
        else:
            for row in results:
                st.markdown(f"**{row['metal']} — {row['extractant']}**")

                c1, c2, c3 = st.columns(3)
                c1.metric("pH range tested", f"{row['pH_min']}–{row['pH_max']}" if row['pH_min'] is not None else "N.R.")
                c2.metric("Highest D reported", f"{row['best_D']:.2f}" if row['best_D'] is not None else "N.R.")
                c3.metric("Highest %E reported", f"{row['best_pctE']:.2f}" if row['best_pctE'] is not None else "N.R.")

                user_conc = metal_inputs[row["metal"]]
                tested = [c for c in row["tested_feed_concs"] if c != "N.R."]
                sources = [s for s in row["waste_sources"] if s is not None]
                st.caption(
                    f"Your input: {user_conc:.2f} g/L  |  "
                    f"Literature feed concentrations tested for this system: "
                    f"{', '.join(tested) if tested else 'none reported'}"
                )
                st.caption(
                    f"Sourced from: {'; '.join(sources) if sources else 'unspecified'}"
                )
                st.divider()

            st.caption(
                "Data drawn from the literature currently loaded into the "
                "knowledge graph. Highest D and highest %E are reported "
                "independently and may come from different experiments; the "
                "CSV export for the optimisation team resolves this by "
                "selecting a single internally consistent best experiment "
                "per system. This tool currently filters by which metals are "
                "present, not their concentration — recommendations are not "
                "yet adjusted based on how much of a metal is in the waste "
                "stream (open scope question for Dr. Zhang)."
            )