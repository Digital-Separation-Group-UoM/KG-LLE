import os
from neo4j import GraphDatabase

# Read credentials from environment variables (never hardcode these)
URI = os.environ["NEO4J_URI"]
USERNAME = os.environ["NEO4J_USERNAME"]
PASSWORD = os.environ["NEO4J_PASSWORD"]

# The "driver" is the object that manages the connection to the database.
# Think of this like opening a connection/socket to a remote server.
driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

# A "session" is a single conversation with the database, similar to
# how you'd open a session with a MATLAB engine to run commands.
with driver.session() as session:
    # This runs a trivial Cypher query just to prove the connection works.
    # Cypher is Neo4j's query language, similar in role to SQL for
    # regular databases — we'll build up real Cypher soon.
    result = session.run("RETURN 'Connection successful!' AS message")
    record = result.single()
    print(record["message"])

driver.close()