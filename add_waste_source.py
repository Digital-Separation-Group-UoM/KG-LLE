import os
from neo4j import GraphDatabase

URI = os.environ["NEO4J_URI"]
USERNAME = os.environ["NEO4J_USERNAME"]
PASSWORD = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

# Built directly from evidence checked against each paper's actual PDF text
# (or title, for the two papers not locally saved). Nothing here is guessed -
# see the waste-source investigation for the specific sentences each value
# is based on.
WASTE_SOURCES = {
    "10.5277/ppmp/193742": {
        "name": "Smelted metallic alloy from spent LIBs",
        "cathode_chemistry": "unspecified",
        "is_synthetic": True,
    },
    "10.3390/met12091445": {
        "name": "Spent LIB leachate (NMC-associated)",
        "cathode_chemistry": "NMC",
        "is_synthetic": False,
    },
    "10.3390/met12050882": {
        "name": "Spent LIB leachate (unspecified chemistry)",
        "cathode_chemistry": "unspecified",
        "is_synthetic": False,
    },
    "10.3390/met14030345": {
        "name": "Spent LIB effluent (unspecified chemistry)",
        "cathode_chemistry": "unspecified",
        "is_synthetic": False,
    },
    "10.3390/min13020285": {
        "name": "Spent LIB leachate (NMC-family/ternary cathode)",
        "cathode_chemistry": "NMC",
        "is_synthetic": False,
    },
    "10.3390/min10080662": {
        "name": "Spent LIB cathode material (NMC), synthetic solution",
        "cathode_chemistry": "NMC",
        "is_synthetic": True,
    },
}


def main():
    with driver.session() as session:
        for doi, info in WASTE_SOURCES.items():
            session.run(
                """
                MATCH (p:Paper {doi: $doi})
                MERGE (w:WasteSource {name: $name})
                SET w.cathode_chemistry = $chem,
                    w.is_synthetic = $synthetic
                MERGE (p)-[:SOURCED_FROM]->(w)
                """,
                doi=doi, name=info["name"],
                chem=info["cathode_chemistry"], synthetic=info["is_synthetic"]
            )
            print(f"{doi}  ->  {info['name']}")

    driver.close()


if __name__ == "__main__":
    main()