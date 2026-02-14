.PHONY: install setup ingest search eval clean test lint

install:
	poetry install

setup: install
	poetry run python -c "from neo4j_rag.config import settings; from neo4j import GraphDatabase; \
		d = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)); \
		s = d.session(database=settings.neo4j_database); \
		[s.run(q) for q in open('scripts/setup_indexes.cypher').read().split(';') if q.strip() and not q.strip().startswith('//')]; \
		d.close(); print('Indexes created.')"

ingest:
	poetry run neo4j-rag ingest --dir ./data/materiais/

search:
	@echo "Usage: make search Q='sua pergunta aqui'"
	poetry run neo4j-rag search "$(Q)"

eval:
	poetry run neo4j-rag eval --dataset ./tests/golden_qa.jsonl

test:
	poetry run pytest tests/ -v

lint:
	poetry run ruff check neo4j_rag/ tests/

clean:
	poetry run python -c "from neo4j_rag.config import settings; from neo4j import GraphDatabase; \
		d = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)); \
		s = d.session(database=settings.neo4j_database); \
		s.run('MATCH (n) DETACH DELETE n'); d.close(); print('Database cleared.')"
