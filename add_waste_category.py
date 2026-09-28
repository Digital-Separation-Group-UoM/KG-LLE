import os
from neo4j import GraphDatabase

URI = os.environ["NEO4J_URI"]
USERNAME = os.environ["NEO4J_USERNAME"]
PASSWORD = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

# Classifies each WasteSource into one of three categories, based on
# fields already set when the node was created (is_synthetic, and
# whether it's a WEEE source vs a battery source).
def classify_category(name, is_synthetic):
    n = name.lower()
    if "weee" in n:
        return "WEEE"
    if is_synthetic:
        return "synthetic battery-derived"
    return "real battery leachate"


def main():
    with driver.session() as session:
        result = session.run(
            "MATCH (w:WasteSource) RETURN w.name AS name, w.is_synthetic AS is_synthetic"
        )
        sources = result.data()

        print(f"Found {len(sources)} distinct waste sources.\n")

        for s in sources:
            category = classify_category(s["name"], s["is_synthetic"])
            session.run(
                "MATCH (w:WasteSource {name: $name}) SET w.waste_category = $category",
                name=s["name"], category=category
            )
            print(f"{s['name']}  ->  {category}")

    driver.close()


if __name__ == "__main__":
    main()