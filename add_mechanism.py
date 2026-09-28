import os
from neo4j import GraphDatabase

URI = os.environ["NEO4J_URI"]
USERNAME = os.environ["NEO4J_USERNAME"]
PASSWORD = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

# Mechanism classification, based on the chemistry each extractant is
# known to use. Matched by keyword rather than exact name, since the same
# base chemical appears under several name variants in the graph
# (e.g. "Cyanex 272", "Cyanex 272 (30% saponified)", "Cyanex272 (sodium
# salt)" should all classify the same way).
def classify_mechanism(name):
    n = name.lower()
    if "cyanex" in n:
        return "cation exchange"
    if "d2ehpa" in n or "p-204" in n:
        return "cation exchange"
    if "pc-88a" in n or "p-507" in n:
        return "cation exchange"
    if "lix 84" in n:
        return "chelation"
    if "versatic" in n:
        return "cation exchange"
    if "lix 984" in n:
        return "chelation"
    if n.strip().startswith("ha ") or n.strip() == "ha":
        return "cation exchange"
    return "unclassified" # flagged for manual review, not guessed


def main():
    with driver.session() as session:
        result = session.run("MATCH (e:Extractant) RETURN e.name AS name")
        names = [r["name"] for r in result]

        print(f"Found {len(names)} distinct extractants.\n")

        for name in names:
            mechanism = classify_mechanism(name)
            session.run(
                "MATCH (e:Extractant {name: $name}) SET e.mechanism = $mechanism",
                name=name, mechanism=mechanism
            )
            print(f"{name}  ->  {mechanism}")

    driver.close()


if __name__ == "__main__":
    main()