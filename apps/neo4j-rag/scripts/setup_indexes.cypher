// ============================================================
// Neo4j Indexes for neo4j-rag standalone app
// Run once after creating the database.
// ============================================================

// --- Vector Index (HNSW, voyage-4-large = 1024 dimensions) ---
CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
FOR (c:Chunk) ON c.embedding
OPTIONS {indexConfig: {
  `vector.dimensions`: 1024,
  `vector.similarity_function`: 'cosine'
}};

// --- Fulltext Index (BM25 with brazilian analyzer) ---
// Note: if 'brazilian' analyzer is not available, use 'standard'
CREATE FULLTEXT INDEX chunk_fulltext IF NOT EXISTS
FOR (c:Chunk) ON EACH [c.text]
OPTIONS {indexConfig: {
  `fulltext.analyzer`: 'brazilian'
}};

// --- Entity lookup indexes ---
CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.normalized_name);
CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.entity_type);

// --- Document lookup ---
CREATE INDEX document_id IF NOT EXISTS FOR (d:Document) ON (d.id);

// --- Chunk lookup ---
CREATE INDEX chunk_id IF NOT EXISTS FOR (c:Chunk) ON (c.id);
CREATE INDEX chunk_doc IF NOT EXISTS FOR (c:Chunk) ON (c.doc_id);

// --- Constraint: unique IDs ---
CREATE CONSTRAINT chunk_unique_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT document_unique_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE;
CREATE CONSTRAINT entity_unique_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;
