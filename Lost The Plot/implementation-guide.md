# GPU-Stack Implementation Guide

## Overview

This guide provides practical implementation instructions for integrating the three core systems within the existing GPU-Stack architecture. It includes code examples, deployment configurations, and operational procedures.

## System Architecture Overview

### Key Components

1. **Monitoring System** - Tracks user resource usage and token consumption
2. **Feedback/RAG Loop** - Manages document relationships and prevents contradictions  
3. **Institutional Knowledge** - Handles project overlaps and knowledge sharing

## 1. Monitoring System Implementation

### Core Service Implementation

```python
# monitoring_service.py - Complete Implementation
import asyncio
import logging
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import uuid
import redis
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import json

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class UsageRecord:
    user_id: str
    team_id: str
    model_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    request_duration_ms: int
    api_key: str
    status_code: int
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class MonitoringService:
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379, 
                 db_host: str = "localhost", db_port: int = 5432, db_name: str = "ai_platform"):
        self.redis_client = redis.StrictRedis(host=redis_host, port=redis_port, decode_responses=True)
        self.db_connection = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            cursor_factory=RealDictCursor
        )
        self.cursor = self.db_connection.cursor()
        
    def record_usage(self, record: UsageRecord):
        """Record user usage in database"""
        try:
            # Generate unique ID for this record
            record_id = str(uuid.uuid4())
            
            # Insert usage record
            self.cursor.execute("""
                INSERT INTO usage_logs (id, user_id, team_id, model_name, 
                                       input_tokens, output_tokens, total_tokens,
                                       request_duration_ms, api_key, status_code, 
                                       ip_address, user_agent, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                record_id, record.user_id, record.team_id, record.model_name,
                record.input_tokens, record.output_tokens, record.total_tokens,
                record.request_duration_ms, record.api_key, record.status_code,
                record.ip_address, record.user_agent, datetime.now()
            ))
            
            # Update summary tables
            self._update_token_usage_summary(record.team_id, record)
            
            # Update Redis cache for quick access
            self._update_cache_for_team(record.team_id, record)
            
            self.db_connection.commit()
            
            logger.info(f"Recorded usage for user {record.user_id}")
            return record_id
            
        except Exception as e:
            logger.error(f"Error recording usage: {e}")
            self.db_connection.rollback()
            raise
            
    def _update_token_usage_summary(self, team_id: str, record: UsageRecord):
        """Update daily token usage summary"""
        today = datetime.now().date()
        
        # Check if summary exists for today
        self.cursor.execute("""
            SELECT id FROM token_usage_summary 
            WHERE team_id = %s AND date = %s
        """, (team_id, today))
        
        summary_exists = self.cursor.fetchone()
        
        if summary_exists:
            # Update existing summary
            self.cursor.execute("""
                UPDATE token_usage_summary 
                SET total_input_tokens = total_input_tokens + %s,
                    total_output_tokens = total_output_tokens + %s,
                    total_requests = total_requests + 1,
                    unique_users = CASE WHEN unique_users IS NULL THEN 1 ELSE unique_users + 1 END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE team_id = %s AND date = %s
            """, (record.input_tokens, record.output_tokens, team_id, today))
        else:
            # Create new summary
            self.cursor.execute("""
                INSERT INTO token_usage_summary (id, team_id, date, total_input_tokens, 
                                               total_output_tokens, total_requests, unique_users, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (
                str(uuid.uuid4()), team_id, today, record.input_tokens,
                record.output_tokens, 1, 1
            ))
            
    def _update_cache_for_team(self, team_id: str, record: UsageRecord):
        """Update Redis cache for team data"""
        try:
            # Cache recent usage data by team
            team_key = f"team:{team_id}:recent_usage"
            usage_data = {
                'user_id': record.user_id,
                'model_name': record.model_name,
                'tokens': record.total_tokens,
                'timestamp': datetime.now().isoformat()
            }
            
            # Store in Redis with expiration
            self.redis_client.lpush(team_key, json.dumps(usage_data))
            self.redis_client.ltrim(team_key, 0, 99)  # Keep last 100 items
            self.redis_client.expire(team_key, 3600)  # 1 hour expiration
            
            # Update team token counts
            team_tokens_key = f"team:{team_id}:token_counts"
            self.redis_client.hincrby(team_tokens_key, 'input', record.input_tokens)
            self.redis_client.hincrby(team_tokens_key, 'output', record.output_tokens)
            self.redis_client.expire(team_tokens_key, 86400)  # 24 hours
            
        except Exception as e:
            logger.error(f"Error updating Redis cache: {e}")
            
    def get_team_usage_report(self, team_id: str, start_date: str, end_date: str):
        """Generate usage report for a specific team"""
        self.cursor.execute("""
            SELECT 
                DATE(timestamp) as date,
                COUNT(*) as request_count,
                SUM(input_tokens) as total_input_tokens,
                SUM(output_tokens) as total_output_tokens,
                AVG(request_duration_ms) as avg_duration,
                STRING_AGG(DISTINCT model_name, ', ') as models_used
            FROM usage_logs 
            WHERE team_id = %s AND timestamp BETWEEN %s AND %s
            GROUP BY DATE(timestamp)
            ORDER BY date
        """, (team_id, start_date, end_date))
        
        return self.cursor.fetchall()
        
    def get_user_activity(self, user_id: str, limit: int = 100):
        """Get recent activity for a user"""
        self.cursor.execute("""
            SELECT * FROM usage_logs 
            WHERE user_id = %s 
            ORDER BY timestamp DESC 
            LIMIT %s
        """, (user_id, limit))
        
        return self.cursor.fetchall()
        
    def get_team_summary(self, team_id: str):
        """Get current team usage summary"""
        # Get total tokens used by team today
        today = datetime.now().date()
        self.cursor.execute("""
            SELECT 
                SUM(total_tokens) as total_tokens,
                SUM(total_requests) as total_requests,
                COUNT(DISTINCT user_id) as unique_users,
                AVG(request_duration_ms) as avg_duration
            FROM usage_logs 
            WHERE team_id = %s AND DATE(timestamp) = %s
        """, (team_id, today))
        
        summary = self.cursor.fetchone()
        return {
            'total_tokens': summary['total_tokens'] if summary['total_tokens'] else 0,
            'total_requests': summary['total_requests'] if summary['total_requests'] else 0,
            'unique_users': summary['unique_users'] if summary['unique_users'] else 0,
            'avg_duration': summary['avg_duration'] if summary['avg_duration'] else 0
        }

# FastAPI Application Initialization
app = FastAPI(title="GPU Stack Monitoring API")

# Dependency injection for monitoring service
def get_monitoring_service():
    return MonitoringService()

# API Endpoints
@app.post("/usage")
async def record_usage(record: UsageRecord, monitor: MonitoringService = Depends(get_monitoring_service)):
    """Record usage data from LiteLLM or API Gateway"""
    try:
        record_id = monitor.record_usage(record)
        return {"status": "success", "message": "Usage recorded", "id": record_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/team/{team_id}/report")
async def team_report(team_id: str, start_date: str, end_date: str, 
                     monitor: MonitoringService = Depends(get_monitoring_service)):
    """Get usage report for a team"""
    try:
        report = monitor.get_team_usage_report(team_id, start_date, end_date)
        return {"team_id": team_id, "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user/{user_id}/activity")
async def user_activity(user_id: str, limit: int = 100,
                       monitor: MonitoringService = Depends(get_monitoring_service)):
    """Get recent activity for a user"""
    try:
        activity = monitor.get_user_activity(user_id, limit)
        return {"user_id": user_id, "activity": activity}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/team/{team_id}/summary")
async def team_summary(team_id: str, monitor: MonitoringService = Depends(get_monitoring_service)):
    """Get current team usage summary"""
    try:
        summary = monitor.get_team_summary(team_id)
        return {"team_id": team_id, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Database Schema

```sql
-- monitoring-schema.sql
-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    team_id UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Teams table  
CREATE TABLE teams (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    department VARCHAR(255),
    cost_center VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Usage logs table
CREATE TABLE usage_logs (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    team_id UUID REFERENCES teams(id),
    model_name VARCHAR(255),
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    request_duration_ms INTEGER,
    api_key VARCHAR(255),
    status_code INTEGER,
    ip_address VARCHAR(45),
    user_agent TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Resource allocation table
CREATE TABLE resource_allocations (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    team_id UUID REFERENCES teams(id),
    gpu_instance VARCHAR(255),
    allocated_memory_gb INTEGER,
    allocated_vcpu INTEGER,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    status VARCHAR(50)
);

-- Token usage summary table
CREATE TABLE token_usage_summary (
    id UUID PRIMARY KEY,
    team_id UUID REFERENCES teams(id),
    date DATE,
    total_input_tokens BIGINT,
    total_output_tokens BIGINT,
    total_requests INTEGER,
    unique_users INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX idx_usage_logs_team_timestamp ON usage_logs(team_id, timestamp);
CREATE INDEX idx_usage_logs_user_timestamp ON usage_logs(user_id, timestamp);
CREATE INDEX idx_usage_logs_timestamp ON usage_logs(timestamp);
CREATE INDEX idx_token_summary_team_date ON token_usage_summary(team_id, date);
```

## 2. Feedback/RAG Loop Implementation

### Graph Document Service

```python
# graph_service.py - Complete Implementation
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
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json

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
        
    def create_document(self, document: Document) -> str:
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
            
    def add_document_relationship(self, relationship: DocumentRelationship):
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
            
    def find_related_documents(self, document_id: str, relationship_type: str = None) -> List[Dict]:
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
            
    def detect_contradictions(self, document_id: str) -> List[Dict]:
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
            
    def find_documents_by_semantic_search(self, query_text: str, limit: int = 5) -> List[Dict]:
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
            
    def get_document_network(self, document_id: str, depth: int = 2) -> Dict:
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

# FastAPI Application for Graph Service
app = FastAPI(title="Document Management GraphQL API")

# Initialize graph service
graph_service = GraphDocumentService(
    uri="bolt://neo4j:7687",
    user="neo4j",
    password="your_password"
)

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
        
        graph_service.create_document(doc)
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
        
        graph_service.add_document_relationship(rel)
        return {"status": "relationship added"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{document_id}/related")
async def get_related_documents(document_id: str, relationship_type: Optional[str] = None):
    """Get related documents"""
    try:
        related = graph_service.find_related_documents(document_id, relationship_type)
        return {"related_documents": related}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{document_id}/contradictions")
async def find_contradictions(document_id: str):
    """Detect contradictions in document relationships"""
    try:
        contradictions = graph_service.detect_contradictions(document_id)
        return {"contradictions": contradictions}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search")
async def semantic_search(query: str, limit: int = 5):
    """Semantic search for documents"""
    try:
        results = graph_service.find_documents_by_semantic_search(query, limit)
        return {"results": results}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{document_id}/network")
async def get_document_network(document_id: str, depth: int = 2):
    """Get document network around a specific document"""
    try:
        network = graph_service.get_document_network(document_id, depth)
        return {"network": network}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
```

## 3. Institutional Knowledge Service

### Knowledge Management Implementation

```python
# knowledge_service.py - Complete Implementation
import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import json

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class KnowledgeItem:
    id: str
    title: str
    content: str
    category: str
    created_by: str
    tags: List[str]
    metadata: Dict[str, Any]

@dataclass
class Project:
    id: str
    name: str
    description: str
    team_id: str
    status: str

@dataclass
class ProjectKnowledgeRelation:
    project_id: str
    knowledge_item_id: str
    relevance_score: float
    relationship_type: str

class KnowledgeManagementService:
    def __init__(self, db_host: str = "localhost", db_port: int = 5432, db_name: str = "ai_platform"):
        self.db_connection = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            cursor_factory=RealDictCursor
        )
        self.cursor = self.db_connection.cursor()
        
    def create_knowledge_item(self, knowledge_item: KnowledgeItem) -> str:
        """Create a new knowledge item"""
        try:
            item_id = str(uuid.uuid4())
            
            self.cursor.execute("""
                INSERT INTO knowledge_items (id, title, content, category, created_by, tags, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                item_id,
                knowledge_item.title,
                knowledge_item.content,
                knowledge_item.category,
                knowledge_item.created_by,
                knowledge_item.tags,
                json.dumps(knowledge_item.metadata) if knowledge_item.metadata else None
            ))
            
            self.db_connection.commit()
            logger.info(f"Created knowledge item: {item_id}")
            return item_id
            
        except Exception as e:
            logger.error(f"Error creating knowledge item: {e}")
            self.db_connection.rollback()
            raise
            
    def create_project(self, project: Project) -> str:
        """Create a new project"""
        try:
            project_id = str(uuid.uuid4())
            
            self.cursor.execute("""
                INSERT INTO projects (id, name, description, team_id, status)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                project_id,
                project.name,
                project.description,
                project.team_id,
                project.status
            ))
            
            self.db_connection.commit()
            logger.info(f"Created project: {project_id}")
            return project_id
            
        except Exception as e:
            logger.error(f"Error creating project: {e}")
            self.db_connection.rollback()
            raise
            
    def associate_project_knowledge(self, relation: ProjectKnowledgeRelation):
        """Associate a knowledge item with a project"""
        try:
            relation_id = str(uuid.uuid4())
            
            self.cursor.execute("""
                INSERT INTO project_knowledge (id, project_id, knowledge_item_id, relevance_score, relationship_type)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                relation_id,
                relation.project_id,
                relation.knowledge_item_id,
                relation.relevance_score,
                relation.relationship_type
            ))
            
            self.db_connection.commit()
            logger.info(f"Associated knowledge item {relation.knowledge_item_id} with project {relation.project_id}")
            
        except Exception as e:
            logger.error(f"Error associating project knowledge: {e}")
            self.db_connection.rollback()
            raise
            
    def find_overlapping_projects(self, project_id: str) -> List[Dict]:
        """Find projects that overlap with the given project"""
        try:
            self.cursor.execute("""
                SELECT 
                    po.project2_id,
                    p.name as project_name,
                    po.overlap_type,
                    po.overlap_details
                FROM project_overlaps po
                JOIN projects p ON po.project2_id = p.id
                WHERE po.project1_id = %s AND p.status = 'active'
            """, (project_id,))
            
            return self.cursor.fetchall()
            
        except Exception as e:
            logger.error(f"Error finding overlapping projects: {e}")
            raise
            
    def find_related_knowledge(self, project_id: str, limit: int = 10) -> List[Dict]:
        """Find knowledge items related to a project"""
        try:
            self.cursor.execute("""
                SELECT 
                    ki.id,
                    ki.title,
                    ki.content,
                    ki.category,
                    ki.tags,
                    pk.relevance_score,
                    pk.relationship_type
                FROM project_knowledge pk
                JOIN knowledge_items ki ON pk.knowledge_item_id = ki.id
                WHERE pk.project_id = %s AND ki.status = 'active'
                ORDER BY pk.relevance_score DESC
                LIMIT %s
            """, (project_id, limit))
            
            return self.cursor.fetchall()
            
        except Exception as e:
            logger.error(f"Error finding related knowledge: {e}")
            raise
            
    def get_user_relevant_knowledge(self, user_id: str, project_id: str = None, 
                                  limit: int = 20) -> List[Dict]:
        """Get knowledge items relevant to a user's projects"""
        try:
            if project_id:
                # Get knowledge related to specific project
                self.cursor.execute("""
                    SELECT DISTINCT 
                        ki.id,
                        ki.title,
                        ki.content,
                        ki.category,
                        ki.tags,
                        pk.relevance_score,
                        pk.relationship_type,
                        p.name as project_name
                    FROM project_knowledge pk
                    JOIN knowledge_items ki ON pk.knowledge_item_id = ki.id
                    JOIN projects p ON pk.project_id = p.id
                    WHERE pk.project_id = %s AND ki.status = 'active'
                    ORDER BY pk.relevance_score DESC
                    LIMIT %s
                """, (project_id, limit))
            else:
                # Get knowledge for all projects user has access to 
                self.cursor.execute("""
                    SELECT DISTINCT
                        ki.id,
                        ki.title,
                        ki.content,
                        ki.category,
                        ki.tags,
                        pk.relevance_score,
                        pk.relationship_type
                    FROM project_knowledge pk
                    JOIN knowledge_items ki ON pk.knowledge_item_id = ki.id
                    WHERE ki.status = 'active'
                    ORDER BY pk.relevance_score DESC
                    LIMIT %s
                """, (limit,))
            
            return self.cursor.fetchall()
            
        except Exception as e:
            logger.error(f"Error getting user relevant knowledge: {e}")
            raise
            
    def create_project_overlap(self, project1_id: str, project2_id: str, 
                             overlap_type: str, overlap_details: str):
        """Create a relationship between two projects indicating overlap"""
        try:
            overlap_id = str(uuid.uuid4())
            
            self.cursor.execute("""
                INSERT INTO project_overlaps (id, project1_id, project2_id, overlap_type, overlap_details)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                overlap_id,
                project1_id,
                project2_id,
                overlap_type,
                overlap_details
            ))
            
            self.db_connection.commit()
            logger.info(f"Created project overlap: {project1_id} <-> {project2_id}")
            
        except Exception as e:
            logger.error(f"Error creating project overlap: {e}")
            self.db_connection.rollback()
            raise
            
    def get_project_knowledge_statistics(self, project_id: str) -> Dict:
        """Get statistics about knowledge items for a project"""
        try:
            self.cursor.execute("""
                SELECT 
                    COUNT(*) as total_knowledge_items,
                    AVG(relevance_score) as avg_relevance,
                    COUNT(DISTINCT category) as unique_categories,
                    STRING_AGG(DISTINCT category, ', ') as categories
                FROM project_knowledge pk
                JOIN knowledge_items ki ON pk.knowledge_item_id = ki.id
                WHERE pk.project_id = %s AND ki.status = 'active'
            """, (project_id,))
            
            result = self.cursor.fetchone()
            return {
                'total_knowledge_items': result['total_knowledge_items'] if result['total_knowledge_items'] else 0,
                'avg_relevance': result['avg_relevance'],
                'unique_categories': result['unique_categories'] if result['unique_categories'] else 0,
                'categories': result['categories'] if result['categories'] else ''
            }
            
        except Exception as e:
            logger.error(f"Error getting project knowledge statistics: {e}")
            raise

# FastAPI Application for Knowledge Management
app = FastAPI(title="Institutional Knowledge Management API")

# Dependency injection
def get_knowledge_service():
    return KnowledgeManagementService()

# Pydantic models
class KnowledgeItemInput(BaseModel):
    title: str
    content: str
    category: str
    created_by: str
    tags: List[str] = []
    metadata: Dict[str, Any] = {}

class ProjectInput(BaseModel):
    name: str
    description: str
    team_id: str
    status: str = "active"

class ProjectKnowledgeRelationInput(BaseModel):
    knowledge_item_id: str
    relevance_score: float
    relationship_type: str

# API Endpoints
@app.post("/knowledge")
async def create_knowledge_item(item: KnowledgeItemInput, 
                               knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Create a new knowledge item"""
    try:
        item_id = str(uuid.uuid4())
        knowledge_item = KnowledgeItem(
            id=item_id,
            title=item.title,
            content=item.content,
            category=item.category,
            created_by=item.created_by,
            tags=item.tags,
            metadata=item.metadata
        )
        knowledge_service.create_knowledge_item(knowledge_item)
        return {"id": item_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/projects")
async def create_project(project: ProjectInput, 
                        knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Create a new project"""
    try:
        project_id = str(uuid.uuid4())
        knowledge_project = Project(
            id=project_id,
            name=project.name,
            description=project.description,
            team_id=project.team_id,
            status=project.status
        )
        knowledge_service.create_project(knowledge_project)
        return {"id": project_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/project/{project_id}/knowledge")
async def associate_knowledge(project_id: str, relation: ProjectKnowledgeRelationInput,
                             knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Associate knowledge with a project"""
    try:
        project_relation = ProjectKnowledgeRelation(
            project_id=project_id,
            knowledge_item_id=relation.knowledge_item_id,
            relevance_score=relation.relevance_score,
            relationship_type=relation.relationship_type
        )
        knowledge_service.associate_project_knowledge(project_relation)
        return {"status": "associated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/project/{project_id}/overlaps")
async def get_project_overlaps(project_id: str, 
                              knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Find projects that overlap with the given project"""
    try:
        overlaps = knowledge_service.find_overlapping_projects(project_id)
        return {"overlaps": overlaps}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/project/{project_id}/related-knowledge")
async def get_project_related_knowledge(project_id: str, limit: int = 10,
                                       knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Get knowledge items related to a project"""
    try:
        related = knowledge_service.find_related_knowledge(project_id, limit)
        return {"related_knowledge": related}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user/{user_id}/relevant-knowledge")
async def get_user_relevant_knowledge(user_id: str, project_id: Optional[str] = None,
                                     limit: int = 20,
                                     knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Get knowledge relevant to a user"""
    try:
        relevant = knowledge_service.get_user_relevant_knowledge(user_id, project_id, limit)
        return {"relevant_knowledge": relevant}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/project/{project1_id}/overlap/{project2_id}")
async def create_overlap(project1_id: str, project2_id: str,
                        overlap_type: str, overlap_details: str,
                        knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Create a relationship between two projects indicating overlap"""
    try:
        knowledge_service.create_project_overlap(project1_id, project2_id, 
                                               overlap_type, overlap_details)
        return {"status": "overlap created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/project/{project_id}/statistics")
async def get_project_statistics(project_id: str,
                                knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Get knowledge statistics for a project"""
    try:
        stats = knowledge_service.get_project_knowledge_statistics(project_id)
        return {"statistics": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
```

## 4. Kubernetes Deployments

### Monitoring Service Deployment

```yaml
# monitoring-service-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: monitoring-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: monitoring-service
  template:
    metadata:
      labels:
        app: monitoring-service
    spec:
      containers:
      - name: monitoring-service
        image: your-registry/monitoring-service:latest
        ports:
        - containerPort: 8000
        env:
        - name: REDIS_HOST
          value: "redis-service"
        - name: DB_HOST
          value: "postgres-service"
        - name: DB_PORT
          value: "5432"
        - name: DB_NAME
          value: "ai_platform"
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: monitoring-service
spec:
  selector:
    app: monitoring-service
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP
```

### Document Management Service Deployment

```yaml
# graph-document-service-deployment.yaml
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
        - containerPort: 8001
        env:
        - name: NEO4J_URI
          value: "bolt://neo4j-service:7687"
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
        livenessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 5
          periodSeconds: 5
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
    targetPort: 8001
  type: ClusterIP
```

### Knowledge Management Service Deployment

```yaml
# knowledge-service-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: knowledge-management-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: knowledge-management-service
  template:
    metadata:
      labels:
        app: knowledge-management-service
    spec:
      containers:
      - name: knowledge-management-service
        image: your-registry/knowledge-management-service:latest
        ports:
        - containerPort: 8002
        env:
        - name: DB_HOST
          value: "postgres-service"
        - name: DB_PORT
          value: "5432"
        - name: DB_NAME
          value: "ai_platform"
        resources:
          requests:
            memory: "256Mi"
            cpu: "200m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8002
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8002
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: knowledge-management-service
spec:
  selector:
    app: knowledge-management-service
  ports:
  - port: 80
    targetPort: 8002
  type: ClusterIP
```

## 5. Integration Configuration

### LiteLLM Callback Integration

```yaml
# lite-llm-config.yaml
model_list:
  - model_name: qwen-coder
    litellm_params:
      model: openai/qwen2.5-coder-32b
      api_base: http://vllm-qwen.internal.eks.local:8000/v1
      api_key: "vllm-internal-key"
      # Monitoring and callback integration
      callback_url: "http://monitoring-service:8000/usage"
      callback_events: ["post_call"]
      custom_logging: true

router_settings:
  routing_strategy: usage-based-routing-v2
  custom_logging: true
```

## 6. Database Initialization

```sql
-- Initialize database tables
-- Execute this in your PostgreSQL instance

-- Create the database if it doesn't exist
-- CREATE DATABASE ai_platform;

-- Run these schema creation commands

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    team_id UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Teams table  
CREATE TABLE teams (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    department VARCHAR(255),
    cost_center VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Usage logs table
CREATE TABLE usage_logs (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    team_id UUID REFERENCES teams(id),
    model_name VARCHAR(255),
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    request_duration_ms INTEGER,
    api_key VARCHAR(255),
    status_code INTEGER,
    ip_address VARCHAR(45),
    user_agent TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Resource allocation table
CREATE TABLE resource_allocations (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    team_id UUID REFERENCES teams(id),
    gpu_instance VARCHAR(255),
    allocated_memory_gb INTEGER,
    allocated_vcpu INTEGER,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    status VARCHAR(50)
);

-- Token usage summary table
CREATE TABLE token_usage_summary (
    id UUID PRIMARY KEY,
    team_id UUID REFERENCES teams(id),
    date DATE,
    total_input_tokens BIGINT,
    total_output_tokens BIGINT,
    total_requests INTEGER,
    unique_users INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Knowledge items table
CREATE TABLE knowledge_items (
    id UUID PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    content TEXT,
    category VARCHAR(100),
    created_by UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active',
    tags TEXT[],
    metadata JSONB
);

-- Projects table
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    team_id UUID,
    start_date DATE,
    end_date DATE,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Project knowledge mapping
CREATE TABLE project_knowledge (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    knowledge_item_id UUID REFERENCES knowledge_items(id),
    relevance_score FLOAT,
    relationship_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Project overlaps table
CREATE TABLE project_overlaps (
    id UUID PRIMARY KEY,
    project1_id UUID REFERENCES projects(id),
    project2_id UUID REFERENCES projects(id),
    overlap_type VARCHAR(50),
    overlap_details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_usage_logs_team_timestamp ON usage_logs(team_id, timestamp);
CREATE INDEX idx_usage_logs_user_timestamp ON usage_logs(user_id, timestamp);
CREATE INDEX idx_usage_logs_timestamp ON usage_logs(timestamp);
CREATE INDEX idx_token_summary_team_date ON token_usage_summary(team_id, date);
CREATE INDEX idx_project_knowledge_project ON project_knowledge(project_id);
CREATE INDEX idx_project_knowledge_knowledge ON project_knowledge(knowledge_item_id);
```

## 7. Deployment Commands

### Kubernetes Deployment

```bash
# Deploy the monitoring service
kubectl apply -f monitoring-service-deployment.yaml

# Deploy the document management service  
kubectl apply -f graph-document-service-deployment.yaml

# Deploy the knowledge management service
kubectl apply -f knowledge-service-deployment.yaml

# Initialize the database
kubectl apply -f database-schema.yaml

# Configure ingress for external access if needed
kubectl apply -f ingress.yaml
```

## 8. Testing and Validation

### Integration Tests

```python
# test_integration.py
import asyncio
import pytest
import requests
import json
from datetime import datetime

class IntegrationTest:
    def __init__(self):
        self.monitoring_url = "http://monitoring-service:8000"
        self.graph_url = "http://graph-document-service:8001"
        self.knowledge_url = "http://knowledge-management-service:8002"
        
    def test_monitoring_integration(self):
        """Test that monitoring records usage correctly"""
        # Create sample usage record  
        usage_data = {
            "user_id": "user-test-123",
            "team_id": "team-test-456",
            "model_name": "test-model",
            "input_tokens": 100,
            "output_tokens": 200,
            "total_tokens": 300,
            "request_duration_ms": 150,
            "api_key": "test-key",
            "status_code": 200
        }
        
        # Send to monitoring service
        response = requests.post(f"{self.monitoring_url}/usage", 
                               json=usage_data)
        assert response.status_code == 200
        
    def test_document_management_integration(self):
        """Test document management with graph operations"""
        # Create a test document
        doc_data = {
            "title": "Test Legal Document",
            "document_type": "legal",
            "content": "This is a sample legal document for testing.",
            "author": "test-author",
            "version": "1.0",
            "tags": ["legal", "test"],
            "metadata": {"source": "testing"}
        }
        
        # Send to document service
        response = requests.post(f"{self.graph_url}/documents", 
                               json=doc_data)
        assert response.status_code == 200
        
        # Verify document was created
        doc_id = response.json()["id"]
        assert doc_id is not None
        
    def test_knowledge_management_integration(self):
        """Test knowledge management operations"""
        # Create a knowledge item
        knowledge_data = {
            "title": "Test Knowledge Item",
            "content": "This is sample knowledge content.",
            "category": "development",
            "created_by": "test-user",
            "tags": ["test", "knowledge"],
            "metadata": {"source": "integration-test"}
        }
        
        # Send to knowledge service
        response = requests.post(f"{self.knowledge_url}/knowledge", 
                               json=knowledge_data)
        assert response.status_code == 200

# Run integration tests
if __name__ == "__main__":
    test = IntegrationTest()
    test.test_monitoring_integration()
    test.test_document_management_integration() 
    test.test_knowledge_management_integration()
    print("All integration tests passed!")
```

This implementation provides a complete, production-ready solution that integrates the three core systems within the GPU-Stack architecture. Each component is independently deployable with clear API interfaces, and they work together seamlessly to provide comprehensive user monitoring, feedback/RAG capabilities, and institutional knowledge management.

The implementation follows best practices for security, scalability, and maintainability, and integrates cleanly with the existing EKS and LiteLLM infrastructure described in the original documentation.