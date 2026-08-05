# Feedback/RAG Loop System for Document Management

## Overview

This document outlines the implementation of a feedback/RAG loop system that enables legal teams to maintain related documents that reference each other without contradictions. The system uses a graph database approach with Neo4j for managing document relationships and semantic embeddings.

## Architecture

The system is built using a graph database approach with Neo4j for managing document relationships and semantic connections, while integrating with Elasticsearch for security logs analysis.

### Components

1. **Document Management Service** - Handles document ingestion, parsing, and metadata extraction
2. **Semantic Indexing System** - Processes documents into embeddings and stores in vector database
3. **Relationship Engine** - Detects and manages document relationships and references
4. **Feedback Processor** - Incorporates user feedback into document processing
5. **Contradiction Detection System** - Identifies inconsistencies in related documents
6. **GraphQL API** - Provides flexible querying for relationships and documents
7. **Elasticsearch Connector** - Integrates security logs with document relationships

## Implementation Plan

### 1. Graph Data Model

#### Core Nodes

```cypher
// Document node
(:Document {
  id: string,
  title: string,
  document_type: string,
  version: string,
  author: string,
  created_at: datetime,
  updated_at: datetime,
  content: string,
  status: string,
  tags: [string],
  metadata: map,
  embedding: [float] // vector embedding
})

// Entity node (for cross-references)
(:Entity {
  id: string,
  type: string,  // user, system, ip_address, policy, etc.
  name: string,
  properties: map
})

// SecurityLog node (for log integration)
(:SecurityLog {
  id: string,
  timestamp: datetime,
  source_ip: string,
  destination_ip: string,
  user: string,
  event_type: string,
  severity: string,
  description: string,
  raw_log: string,
  processed: boolean
})
```

#### Relationship Types

```cypher
// Document relationships
(:Document)-[:REFERENCES]->(:Document)           // Document references another
(:Document)-[:CONTAINS]->(:Document)             // Document contains content from another
(:Document)-[:COMPLIES_WITH]->(:Document)        // Document complies with another
(:Document)-[:SUPERSEDES]->(:Document)           // Document supersedes another

// Entity relationships  
(:Document)-[:INVOLVES]->(:Entity)               // Document involves an entity
(:Entity)-[:MENTIONS]->(:Document)               // Entity mentions a document

// Security relationships
(:SecurityLog)-[:INVOLVES]->(:Entity)            // Log involves an entity
(:SecurityLog)-[:RELATES_TO]->(:Document)        // Log relates to a document

// Cross-domain relationships
(:SecurityLog)-[:RELATES_TO]->(:Document)        // Security log relates to document
(:Document)-[:RELATES_TO]->(:SecurityLog)        // Document relates to security log
```

### 2. Neo4j Integration (Python)

```python
# graph_service.py
import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import uuid
import hashlib
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
import numpy as np

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Document:
    id: str
    title: str
    document_type: str
    content: str
    author: str
    version: str
    tags: List[str]
    metadata: Dict[str, Any]

@dataclass
class DocumentRelationship:
    from_document_id: str
    to_document_id: str
    relationship_type: str
    properties: Dict[str, Any]

class GraphDocumentService:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
    def close(self):
        self.driver.close()
        
    async def create_document(self, document: Document) -> str:
        """Create a new document node in the graph"""
        try:
            # Generate embedding for the document
            embedding = self._generate_embedding(document.content)
            
            # Create document node
            with self.driver.session() as session:
                result = session.run("""
                    CREATE (d:Document {
                        id: $id,
                        title: $title,
                        document_type: $document_type,
                        author: $author,
                        version: $version,
                        content: $content,
                        created_at: $created_at,
                        updated_at: $updated_at,
                        tags: $tags,
                        metadata: $metadata,
                        embedding: $embedding
                    })
                    RETURN d.id
                """, {
                    'id': document.id,
                    'title': document.title,
                    'document_type': document.document_type,
                    'author': document.author,
                    'version': document.version,
                    'content': document.content,
                    'created_at': datetime.now(),
                    'updated_at': datetime.now(),
                    'tags': document.tags,
                    'metadata': document.metadata,
                    'embedding': embedding.tolist()
                })
                
                logger.info(f"Created document with ID: {document.id}")
                return document.id
                
        except Exception as e:
            logger.error(f"Error creating document: {e}")
            raise
            
    async def add_document_relationship(self, relationship: DocumentRelationship):
        """Add a relationship between documents"""
        try:
            with self.driver.session() as session:
                session.run("""
                    MATCH (from:Document {id: $from_id}), (to:Document {id: $to_id})
                    CREATE (from)-[r:%s {
                        relationship_type: $relationship_type,
                        properties: $properties,
                        created_at: $created_at
                    }]->(to)
                    RETURN r
                """ % relationship.relationship_type, {
                    'from_id': relationship.from_document_id,
                    'to_id': relationship.to_document_id,
                    'relationship_type': relationship.relationship_type,
                    'properties': relationship.properties,
                    'created_at': datetime.now()
                })
                
                logger.info(f"Added relationship: {relationship.from_document_id} -> {relationship.to_document_id}")
                
        except Exception as e:
            logger.error(f"Error adding relationship: {e}")
            raise
            
    async def find_related_documents(self, document_id: str, relationship_type: str = None) -> List[Dict]:
        """Find documents related to a given document"""
        try:
            query = """
                MATCH (d:Document {id: $document_id})-[%s]->(related:Document)
                RETURN related
            """
            
            if relationship_type:
                query = query % relationship_type
            else:
                query = query % "*"
                
            with self.driver.session() as session:
                result = session.run(query, {'document_id': document_id})
                return [record['related'].properties for record in result]
                
        except Exception as e:
            logger.error(f"Error finding related documents: {e}")
            raise
            
    async def detect_contradictions(self, document_id: str) -> List[Dict]:
        """Detect contradictory relationships in document network"""
        try:
            # Find all documents related to the target document
            query = """
                MATCH (d1:Document {id: $document_id})-[:REFERENCES]->(d2:Document)
                WHERE (d1)-[:COMPLIES_WITH]->(d2) OR (d2)-[:COMPLIES_WITH]->(d1)
                RETURN d1.id as document1, d2.id as document2, 
                       d1.content as content1, d2.content as content2
            """
            
            with self.driver.session() as session:
                result = session.run(query, {'document_id': document_id})
                contradictions = []
                
                for record in result:
                    # Check content for contradictions using text similarity
                    content1 = record['content1']
                    content2 = record['content2']
                    similarity = self._calculate_similarity(content1, content2)
                    
                    # If similarity is low, consider it contradictory
                    if similarity < 0.3:  # Threshold for contradiction
                        contradictions.append({
                            'document1': record['document1'],
                            'document2': record['document2'],
                            'similarity': similarity,
                            'type': 'content_contradiction'
                        })
                
                return contradictions
                
        except Exception as e:
            logger.error(f"Error detecting contradictions: {e}")
            raise
            
    async def find_documents_by_semantic_search(self, query_text: str, limit: int = 5) -> List[Dict]:
        """Find documents similar to a query using semantic search"""
        try:
            # Generate embedding for query
            query_embedding = self._generate_embedding(query_text)
            
            # Use Neo4j's vector similarity
            with self.driver.session() as session:
                result = session.run("""
                    CALL db.index.vector.queryNodes('document_embedding', $limit, $query_embedding)
                    YIELD node, score
                    RETURN node.id, node.title, node.content, score
                    ORDER BY score DESC
                """, {
                    'query_embedding': query_embedding.tolist(),
                    'limit': limit
                })
                
                return [record.data() for record in result]
                
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            raise
            
    async def get_document_network(self, document_id: str, depth: int = 2) -> Dict:
        """Get the document network around a specific document"""
        try:
            query = """
                MATCH (d:Document {id: $document_id})
                CALL apoc.path.subgraphAll(d, {maxLevel: $depth})
                YIELD nodes, relationships
                RETURN nodes, relationships
            """
            
            with self.driver.session() as session:
                result = session.run(query, {
                    'document_id': document_id,
                    'depth': depth
                })
                
                records = list(result)
                if records:
                    return records[0].data()
                
                return {}
                
        except Exception as e:
            logger.error(f"Error getting document network: {e}")
            raise
            
    def _generate_embedding(self, text: str) -> np.ndarray:
        """Generate semantic embedding for text"""
        return self.embedding_model.encode(text)
        
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using embeddings"""
        embedding1 = self._generate_embedding(text1)
        embedding2 = self._generate_embedding(text2)
        
        # Calculate cosine similarity
        dot_product = np.dot(embedding1, embedding2)
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
            
        return dot_product / (norm1 * norm2)

# GraphQL API Implementation
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Document Management GraphQL API")

# Pydantic models
class DocumentInput(BaseModel):
    title: str
    document_type: str
    content: str
    author: str
    version: str
    tags: List[str] = []
    metadata: Dict[str, Any] = {}

class RelationshipInput(BaseModel):
    from_document_id: str
    to_document_id: str
    relationship_type: str
    properties: Dict[str, Any] = {}

# Initialize graph service
graph_service = GraphDocumentService(
    uri="bolt://neo4j:7687",
    user="neo4j",
    password="your_password"
)

@app.post("/documents")
async def create_document(document: DocumentInput):
    """Create a new document"""
    try:
        doc_id = str(uuid.uuid4())
        doc = Document(
            id=doc_id,
            title=document.title,
            document_type=document.document_type,
            content=document.content,
            author=document.author,
            version=document.version,
            tags=document.tags,
            metadata=document.metadata
        )
        
        await graph_service.create_document(doc)
        return {"id": doc_id, "status": "created"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/{document_id}/relationships")
async def add_relationship(document_id: str, relationship: RelationshipInput):
    """Add relationship between documents"""
    try:
        if relationship.from_document_id != document_id:
            raise HTTPException(status_code=400, detail="from_document_id must match path parameter")
            
        rel = DocumentRelationship(
            from_document_id=relationship.from_document_id,
            to_document_id=relationship.to_document_id,
            relationship_type=relationship.relationship_type,
            properties=relationship.properties
        )
        
        await graph_service.add_document_relationship(rel)
        return {"status": "relationship added"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{document_id}/related")
async def get_related_documents(document_id: str, relationship_type: Optional[str] = None):
    """Get related documents"""
    try:
        related = await graph_service.find_related_documents(document_id, relationship_type)
        return {"related_documents": related}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{document_id}/contradictions")
async def find_contradictions(document_id: str):
    """Detect contradictions in document relationships"""
    try:
        contradictions = await graph_service.detect_contradictions(document_id)
        return {"contradictions": contradictions}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search")
async def semantic_search(query: str, limit: int = 5):
    """Semantic search for documents"""
    try:
        results = await graph_service.find_documents_by_semantic_search(query, limit)
        return {"results": results}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{document_id}/network")
async def get_document_network(document_id: str, depth: int = 2):
    """Get document network around a specific document"""
    try:
        network = await graph_service.get_document_network(document_id, depth)
        return {"network": network}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 3. Elasticsearch Integration

```python
# elasticsearch_integration.py
import logging
from elasticsearch import Elasticsearch
import json
from datetime import datetime
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class ElasticsearchConnector:
    def __init__(self, hosts: List[str], index_prefix: str = "security_logs"):
        self.es = Elasticsearch(hosts=hosts)
        self.index_prefix = index_prefix
        
    def index_security_log(self, log_data: Dict[str, Any]):
        """Index a security log into Elasticsearch"""
        try:
            doc_id = f"{log_data.get('timestamp', '')}_{log_data.get('source_ip', '')}"
            index_name = f"{self.index_prefix}-{datetime.now().strftime('%Y-%m-%d')}"
            
            response = self.es.index(
                index=index_name,
                id=doc_id,
                document=log_data
            )
            
            logger.info(f"Indexed security log with ID: {doc_id}")
            return response
            
        except Exception as e:
            logger.error(f"Error indexing security log: {e}")
            raise
            
    def search_security_logs(self, query: Dict[str, Any], 
                           start_time: str = None, 
                           end_time: str = None) -> List[Dict]:
        """Search security logs in Elasticsearch"""
        try:
            # Build query with time range if provided
            search_query = {
                "query": query
            }
            
            if start_time and end_time:
                search_query["query"]["bool"]["filter"] = [
                    {
                        "range": {
                            "timestamp": {
                                "gte": start_time,
                                "lte": end_time
                            }
                        }
                    }
                ]
            
            result = self.es.search(
                index=f"{self.index_prefix}-*",
                body=search_query
            )
            
            return [hit["_source"] for hit in result["hits"]["hits"]]
            
        except Exception as e:
            logger.error(f"Error searching security logs: {e}")
            raise
            
    def connect_log_to_document(self, log_id: str, document_id: str):
        """Connect a security log to a document in Neo4j"""
        try:
            # This would be called from graph service when creating relationships
            with graph_service.driver.session() as session:
                session.run("""
                    MATCH (log:SecurityLog {id: $log_id}), (doc:Document {id: $document_id})
                    CREATE (log)-[:RELATES_TO]->(doc)
                    RETURN log.id, doc.id
                """, {
                    'log_id': log_id,
                    'document_id': document_id
                })
                
                logger.info(f"Connected log {log_id} to document {document_id}")
                
        except Exception as e:
            logger.error(f"Error connecting log to document: {e}")
            raise
```

### 4. Workflow Integration

#### Document Ingestion Pipeline

```python
# document_pipeline.py
import asyncio
from typing import Dict, Any
from graph_service import GraphDocumentService
from elasticsearch_integration import ElasticsearchConnector

class DocumentProcessingPipeline:
    def __init__(self, graph_service: GraphDocumentService, es_connector: ElasticsearchConnector):
        self.graph_service = graph_service
        self.es_connector = es_connector
        
    async def process_document(self, document_data: Dict[str, Any]) -> str:
        """Process a document through the full pipeline"""
        try:
            # Step 1: Create document in graph
            doc_id = await self._create_document(document_data)
            
            # Step 2: Extract entities and relationships
            entities = self._extract_entities(document_data['content'])
            
            # Step 3: Create entity relationships 
            await self._create_entity_relationships(doc_id, entities)
            
            # Step 4: Find and create document references
            await self._find_document_references(doc_id, document_data['content'])
            
            # Step 5: Check for contradictions
            contradictions = await self._check_for_contradictions(doc_id)
            
            if contradictions:
                logger.warning(f"Contradictions detected in document {doc_id}: {contradictions}")
                # This could trigger an alert or notification
            
            logger.info(f"Successfully processed document: {doc_id}")
            return doc_id
            
        except Exception as e:
            logger.error(f"Error processing document: {e}")
            raise
            
    async def _create_document(self, document_data: Dict[str, Any]) -> str:
        """Create document node in graph"""
        # Implementation from GraphDocumentService.create_document
        pass
        
    def _extract_entities(self, content: str) -> List[Dict[str, Any]]:
        """Extract entities from document content"""
        # Implementation using NLP libraries
        return []
        
    async def _create_entity_relationships(self, doc_id: str, entities: List[Dict[str, Any]]):
        """Create relationships between document and entities"""
        # Implementation to add entities and relationships
        pass
        
    async def _find_document_references(self, doc_id: str, content: str):
        """Find and create document references"""
        # Implementation to detect document references
        pass
        
    async def _check_for_contradictions(self, doc_id: str) -> List[Dict]:
        """Check for contradictions in document relationships"""
        # Implementation from GraphDocumentService.detect_contradictions
        return []
```

## Security and Compliance Features

### Data Protection
- All document data encrypted at rest using AES-256
- TLS 1.3 encryption for all communications
- Access controls via Neo4j RBAC
- Audit logging for all graph access operations

### Compliance
- GDPR compliant data handling
- Data retention policies for documents and logs
- Secure deletion of sensitive information
- Access logging for compliance audits

## Integration with Existing Systems

### API Gateway Integration
Add monitoring endpoints to existing LiteLLM configuration:
```yaml
# LiteLLM config.yaml extension
callbacks:
  - name: "document_tracking_callback"
    url: "http://graph-service:8000/graph/usage"
    events: ["post_call"]
```

### Dashboard Integration
The system provides GraphQL endpoints that can be consumed by:
- Custom dashboards using React/Vue
- Grafana for visualization
- Email notifications for contradictions
- Slack alerts for critical events

## Deployment Instructions

### 1. Neo4j Setup
```bash
# For Neo4j Docker deployment
docker run --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  -e NEO4J_dbms_memory_heap_maxSize=2G \
  -v neo4j-data:/data \
  neo4j:latest
```

### 2. Service Deployment
```yaml
# graph-service-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: graph-document-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: graph-document-service
  template:
    metadata:
      labels:
        app: graph-document-service
    spec:
      containers:
      - name: graph-document-service
        image: your-registry/graph-document-service:latest
        ports:
        - containerPort: 8000
        env:
        - name: NEO4J_URI
          value: "bolt://neo4j:7687"
        - name: NEO4J_USER
          value: "neo4j"
        - name: NEO4J_PASSWORD
          valueFrom:
            secretKeyRef:
              name: neo4j-secret
              key: password
        resources:
          requests:
            memory: "256Mi"
            cpu: "200m"
          limits:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: graph-document-service
spec:
  selector:
    app: graph-document-service
  ports:
  - port: 80
    targetPort: 8000
```

## Monitoring and Maintenance

### Key Metrics
1. **Document Processing**
   - Processing time per document
   - Number of documents processed daily
   - Success/failure rates

2. **Graph Performance**
   - Query response times
   - Node/relationship counts
   - Index performance

3. **Security Integration**
   - Log ingestion rate
   - Log processing accuracy
   - Connection success rates

### Alerts and Notifications
1. **Contradiction Detection**
   - Email alerts when contradictions are detected
   - Slack notifications for critical contradictions

2. **System Health**
   - Neo4j connectivity issues
   - Elasticsearch indexing failures
   - Performance degradation alerts

This implementation provides a robust foundation for a feedback/RAG loop system that maintains document integrity, detects contradictions, and enables semantic relationships between documents while also supporting security log analysis through Elasticsearch integration.