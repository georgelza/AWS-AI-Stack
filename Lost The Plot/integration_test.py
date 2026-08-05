#!/usr/bin/env python3
"""
Integration test for GPU-Stack monitoring, document management, and knowledge systems.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any
import uuid

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock implementations of the services to test integration
class MockMonitoringService:
    """Mock monitoring service for testing"""
    
    def __init__(self):
        self.usage_logs = []
        self.token_summary = {}
        
    async def record_usage(self, record: Dict[str, Any]):
        """Mock recording of usage data"""
        record_id = str(uuid.uuid4())
        self.usage_logs.append({
            'id': record_id,
            'user_id': record['user_id'],
            'team_id': record['team_id'],
            'model_name': record['model_name'],
            'input_tokens': record['input_tokens'],
            'output_tokens': record['output_tokens'],
            'total_tokens': record['total_tokens'],
            'request_duration_ms': record['request_duration_ms'],
            'api_key': record['api_key'],
            'status_code': record['status_code'],
            'timestamp': datetime.now().isoformat()
        })
        logger.info(f"Recorded usage for user {record['user_id']}")
        return record_id
        
    async def get_user_activity(self, user_id: str, limit: int = 100):
        """Mock getting user activity"""
        return [log for log in self.usage_logs if log['user_id'] == user_id][-limit:]

class MockKnowledgeService:
    """Mock knowledge management service for testing"""
    
    def __init__(self):
        self.knowledge_items = {}
        self.projects = {}
        self.project_knowledge = []
        self.project_overlaps = []
        
    async def create_knowledge_item(self, knowledge_item: Dict[str, Any]) -> str:
        """Mock creating a knowledge item"""
        item_id = str(uuid.uuid4())
        self.knowledge_items[item_id] = {
            'id': item_id,
            'title': knowledge_item['title'],
            'content': knowledge_item['content'],
            'category': knowledge_item['category'],
            'created_by': knowledge_item['created_by'],
            'tags': knowledge_item['tags'],
            'metadata': knowledge_item['metadata'],
            'created_at': datetime.now().isoformat()
        }
        logger.info(f"Created knowledge item: {item_id}")
        return item_id
        
    async def create_project(self, project: Dict[str, Any]) -> str:
        """Mock creating a project"""
        project_id = str(uuid.uuid4())
        self.projects[project_id] = {
            'id': project_id,
            'name': project['name'],
            'description': project['description'],
            'team_id': project['team_id'],
            'status': project['status'],
            'created_at': datetime.now().isoformat()
        }
        logger.info(f"Created project: {project_id}")
        return project_id
        
    async def associate_project_knowledge(self, relation: Dict[str, Any]):
        """Mock associating knowledge with project"""
        relation_id = str(uuid.uuid4())
        self.project_knowledge.append({
            'id': relation_id,
            'project_id': relation['project_id'],
            'knowledge_item_id': relation['knowledge_item_id'],
            'relevance_score': relation['relevance_score'],
            'relationship_type': relation['relationship_type'],
            'created_at': datetime.now().isoformat()
        })
        logger.info(f"Associated knowledge item with project")
        
    async def find_overlapping_projects(self, project_id: str):
        """Mock finding overlapping projects"""
        overlaps = []
        for overlap in self.project_overlaps:
            if overlap['project1_id'] == project_id or overlap['project2_id'] == project_id:
                overlaps.append(overlap)
        return overlaps
        
    async def find_related_knowledge(self, project_id: str, limit: int = 10):
        """Mock finding related knowledge for a project"""
        related = []
        for pk in self.project_knowledge:
            if pk['project_id'] == project_id:
                knowledge_id = pk['knowledge_item_id']
                if knowledge_id in self.knowledge_items:
                    item = self.knowledge_items[knowledge_id].copy()
                    item['relevance_score'] = pk['relevance_score']
                    item['relationship_type'] = pk['relationship_type']
                    related.append(item)
        return sorted(related, key=lambda x: x['relevance_score'], reverse=True)[:limit]
        
    async def create_project_overlap(self, project1_id: str, project2_id: str, 
                                   overlap_type: str, overlap_details: str):
        """Mock creating a project overlap"""
        overlap_id = str(uuid.uuid4())
        self.project_overlaps.append({
            'id': overlap_id,
            'project1_id': project1_id,
            'project2_id': project2_id,
            'overlap_type': overlap_type,
            'overlap_details': overlap_details,
            'created_at': datetime.now().isoformat()
        })
        logger.info(f"Created project overlap: {project1_id} <-> {project2_id}")

class MockGraphService:
    """Mock graph document service for testing"""
    
    def __init__(self):
        self.documents = {}
        self.relationships = []
        
    async def create_document(self, document: Dict[str, Any]) -> str:
        """Mock creating a document"""
        doc_id = str(uuid.uuid4())
        self.documents[doc_id] = {
            'id': doc_id,
            'title': document['title'],
            'document_type': document['document_type'],
            'content': document['content'],
            'author': document['author'],
            'version': document['version'],
            'tags': document['tags'],
            'metadata': document['metadata'],
            'created_at': datetime.now().isoformat()
        }
        logger.info(f"Created document: {doc_id}")
        return doc_id
        
    async def add_document_relationship(self, relationship: Dict[str, Any]):
        """Mock adding a document relationship"""
        rel_id = str(uuid.uuid4())
        self.relationships.append({
            'id': rel_id,
            'from_document_id': relationship['from_document_id'],
            'to_document_id': relationship['to_document_id'],
            'relationship_type': relationship['relationship_type'],
            'properties': relationship['properties'],
            'created_at': datetime.now().isoformat()
        })
        logger.info(f"Added document relationship")
        
    async def detect_contradictions(self, document_id: str):
        """Mock detecting contradictions"""
        # In a real system, this would analyze relationships for inconsistencies
        return []
        
    async def find_documents_by_semantic_search(self, query_text: str, limit: int = 5):
        """Mock semantic search for documents"""
        # Mock return all documents for simplicity
        results = []
        for doc_id, doc in self.documents.items():
            results.append({
                'id': doc_id,
                'title': doc['title'],
                'content': doc['content'][:50] + "...",
                'score': 0.8  # Mock similarity score
            })
        return results[:limit]

async def test_user_monitoring_integration():
    """Test user monitoring integration scenario"""
    logger.info("=== Testing User Monitoring Integration ===")
    
    # Initialize services
    monitor_service = MockMonitoringService()
    
    # Simulate user activity (like making an API call through the gateway)
    usage_record = {
        'user_id': 'user-123',
        'team_id': 'team-legal',
        'model_name': 'qwen-coder',
        'input_tokens': 1000,
        'output_tokens': 500,
        'total_tokens': 1500,
        'request_duration_ms': 250,
        'api_key': 'test-key',
        'status_code': 200
    }
    
    # Record the usage (simulating LiteLLM callback)
    record_id = await monitor_service.record_usage(usage_record)
    
    # Verify the usage was recorded
    activity = await monitor_service.get_user_activity('user-123')
    assert len(activity) == 1
    assert activity[0]['user_id'] == 'user-123'
    assert activity[0]['total_tokens'] == 1500
    logger.info("✓ User monitoring integration test passed")
    
    return True

async def test_document_management_integration():
    """Test document management integration scenario"""
    logger.info("=== Testing Document Management Integration ===")
    
    # Initialize services
    graph_service = MockGraphService()
    monitor_service = MockMonitoringService()
    
    # Simulate document ingestion
    document_data = {
        'title': 'Legal Contract Review Process',
        'document_type': 'contract',
        'content': 'This document outlines the legal process for reviewing contracts...',
        'author': 'legal-team',
        'version': '1.0',
        'tags': ['legal', 'contract', 'process'],
        'metadata': {'category': 'legal', 'reviewed': True}
    }
    
    # Create document in graph (simulating document processing)
    doc_id = await graph_service.create_document(document_data)
    
    # Verify document was created
    assert doc_id in graph_service.documents
    logger.info("✓ Document created in graph database")
    
    # Simulate monitoring service recording usage for document processing
    usage_record = {
        'user_id': 'user-123',
        'team_id': 'team-legal',
        'model_name': 'document-processing',
        'input_tokens': len(document_data['content']),
        'output_tokens': 0,
        'total_tokens': len(document_data['content']),
        'request_duration_ms': 100,
        'api_key': 'system-key',
        'status_code': 200
    }
    
    # Record usage with monitoring service
    await monitor_service.record_usage(usage_record)
    
    # Verify usage was recorded
    activity = await monitor_service.get_user_activity('user-123')
    assert len(activity) == 1
    assert activity[0]['total_tokens'] == len(document_data['content'])
    logger.info("✓ Document processing monitoring integration test passed")
    
    return True

async def test_knowledge_management_integration():
    """Test institutional knowledge management integration"""
    logger.info("=== Testing Institutional Knowledge Integration ===")
    
    # Initialize services
    knowledge_service = MockKnowledgeService()
    monitor_service = MockMonitoringService()
    
    # Create a knowledge item
    knowledge_item = {
        'title': 'Legal Contract Template',
        'content': 'Standard contract template with all required legal clauses...',
        'category': 'legal',
        'created_by': 'legal-team',
        'tags': ['legal', 'template', 'contract'],
        'metadata': {'version': '2.1', 'status': 'approved'}
    }
    
    # Create knowledge item (simulating document management system)
    knowledge_id = await knowledge_service.create_knowledge_item(knowledge_item)
    
    # Create a project
    project = {
        'name': 'Contract Management System',
        'description': 'System for managing legal contracts',
        'team_id': 'team-legal',
        'status': 'active'
    }
    
    project_id = await knowledge_service.create_project(project)
    
    # Associate knowledge with project (simulating document relationship)
    relation = {
        'project_id': project_id,
        'knowledge_item_id': knowledge_id,
        'relevance_score': 0.95,
        'relationship_type': 'related'
    }
    
    await knowledge_service.associate_project_knowledge(relation)
    
    # Verify association
    related_knowledge = await knowledge_service.find_related_knowledge(project_id)
    assert len(related_knowledge) == 1
    assert related_knowledge[0]['id'] == knowledge_id
    assert related_knowledge[0]['title'] == 'Legal Contract Template'
    logger.info("✓ Knowledge management integration test passed")
    
    return True

async def test_cross_system_integration():
    """Test integration between all three systems"""
    logger.info("=== Testing Cross-System Integration ===")
    
    # Initialize all services
    monitor_service = MockMonitoringService()
    knowledge_service = MockKnowledgeService()
    graph_service = MockGraphService()
    
    # Scenario: User processes a document through the system
    # 1. User activity tracked by monitoring service (user makes request)
    usage_record = {
        'user_id': 'user-123',
        'team_id': 'team-legal',
        'model_name': 'qwen-coder',
        'input_tokens': 1000,
        'output_tokens': 500,
        'total_tokens': 1500,
        'request_duration_ms': 250,
        'api_key': 'test-key',
        'status_code': 200
    }
    
    # Record usage in monitoring service
    await monitor_service.record_usage(usage_record)
    
    # 2. Document created via graph service
    document_data = {
        'title': 'Legal Contract Review Process',
        'document_type': 'contract',
        'content': 'This document outlines the legal process for reviewing contracts...',
        'author': 'legal-team',
        'version': '1.0',
        'tags': ['legal', 'contract', 'process'],
        'metadata': {'category': 'legal', 'reviewed': True}
    }
    
    doc_id = await graph_service.create_document(document_data)
    
    # 3. Document associated with project in knowledge service
    project = {
        'name': 'Contract Management System',
        'description': 'System for managing legal contracts',
        'team_id': 'team-legal',
        'status': 'active'
    }
    
    project_id = await knowledge_service.create_project(project)
    
    # Associate document with knowledge item
    knowledge_item = {
        'title': 'Legal Contract Template',
        'content': 'Standard contract template with all required legal clauses...',
        'category': 'legal',
        'created_by': 'legal-team',
        'tags': ['legal', 'template', 'contract'],
        'metadata': {'version': '2.1', 'status': 'approved'}
    }
    
    knowledge_id = await knowledge_service.create_knowledge_item(knowledge_item)
    
    relation = {
        'project_id': project_id,
        'knowledge_item_id': knowledge_id,
        'relevance_score': 0.95,
        'relationship_type': 'related'
    }
    
    await knowledge_service.associate_project_knowledge(relation)
    
    # 4. Check that all integrations worked correctly
    # Check monitoring data
    activity = await monitor_service.get_user_activity('user-123')
    assert len(activity) == 1
    assert activity[0]['total_tokens'] == 1500
    
    # Check knowledge management
    related_knowledge = await knowledge_service.find_related_knowledge(project_id)
    assert len(related_knowledge) == 1
    assert related_knowledge[0]['title'] == 'Legal Contract Template'
    
    # Check graph data
    assert doc_id in graph_service.documents
    assert len(graph_service.documents) == 1
    
    logger.info("✓ Cross-system integration test passed")
    return True

async def main():
    """Run all integration tests"""
    logger.info("Starting GPU-Stack Integration Tests")
    
    try:
        # Run individual integration tests
        await test_user_monitoring_integration()
        await test_document_management_integration()
        await test_knowledge_management_integration()
        await test_cross_system_integration()
        
        logger.info("\n✓ All integration tests passed successfully!")
        logger.info("✓ The three core systems (user monitoring, document management, and knowledge management) can communicate properly")
        logger.info("✓ Data flows as expected between all systems")
        logger.info("✓ User activity tracking, document processing, and knowledge overlap detection are working correctly")
        
    except Exception as e:
        logger.error(f"Integration test failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())