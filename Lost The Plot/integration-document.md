# GPU-Stack Integration Document

## Overview

This document provides a comprehensive integration plan that connects the three core systems (user monitoring, feedback/RAG loop, and institutional knowledge management) within the existing GPU-Stack architecture. The integration ensures seamless data flow, unified monitoring, and consistent security practices across all components.

## Architecture Integration

### Component Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   Client Apps   │    │  API Gateway     │    │   LiteLLM        │
│ (IDEs, CLI)     │───▶│ (Axway)         │───▶│ (Proxy)         │
│                 │    │                  │    │                  │
└─────────────────┘    └──────────────────┘    └──────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Monitoring     │    │  Document        │    │  Knowledge       │
│  Service        │    │  Management      │    │  Service         │
│ (Usage Tracking)│    │ (RAG Loop)       │    │ (Project Tracking)│
│                 │    │                  │    │                  │
└─────────────────┘    └──────────────────┘    └──────────────────┘
       │                       │                       │
       │                       │                       │
       ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  PostgreSQL     │    │  Neo4j           │    │  PostgreSQL      │
│ (Structured DB) │    │ (Graph DB)       │    │ (Structured DB)  │
│                 │    │                  │    │                  │
└─────────────────┘    └──────────────────┘    └──────────────────┘
       │                       │                       │
       │                       │                       │
       ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Redis Cache    │    │  Elasticsearch   │    │  Redis Cache     │
│ (Caching)       │    │ (Security Logs)  │    │ (Caching)        │
│                 │    │                  │    │                  │
└─────────────────┘    └──────────────────┘    └──────────────────┘
```

## Integration Points

### 1. Monitoring System Integration

#### Data Flow Integration
The monitoring service integrates with the existing LiteLLM proxy and API Gateway:

1. **LiteLLM Integration**:
   - Add monitoring callback hooks to LiteLLM configuration
   - Capture usage metrics from each request
   - Forward authentication data to monitoring service

2. **API Gateway Integration**:
   - Collect authentication events from Axway API Gateway
   - Monitor rate limiting and quota enforcement
   - Capture IP addresses and request metadata

3. **Usage Reporting**:
   - Generate daily usage reports for teams
   - Create token usage summaries by team
   - Provide cost allocation reports for legal/finance teams

#### Configuration Example

```yaml
# LiteLLM config.yaml with monitoring integration
model_list:
  - model_name: qwen-coder
    litellm_params:
      model: openai/qwen2.5-coder-32b
      api_base: http://vllm-qwen.internal.eks.local:8000/v1
      api_key: "vllm-internal-key"
      # Monitoring integration
      callback_url: "http://monitoring-service:8000/usage"
      callback_events: ["post_call", "pre_call"]

router_settings:
  routing_strategy: usage-based-routing-v2
  # Add logging and monitoring hooks
  custom_logging: true
  monitor_usage: true
```

### 2. Feedback/RAG Loop Integration

#### Document Management Integration
The graph-based document management system integrates with both document processing and security log analysis:

1. **Document Ingestion Pipeline**:
   - Process legal documents through content extraction
   - Generate semantic embeddings for each document
   - Create entity and relationship nodes in Neo4j

2. **Security Log Integration**:
   - Connect Elasticsearch security logs to Neo4j documents
   - Create relationships between security events and related documents
   - Enable cross-domain correlation analysis

3. **Contradiction Detection**:
   - Monitor document relationships for inconsistencies
   - Alert legal teams about contradictory documents
   - Provide tools for resolving document conflicts

#### API Integration

```python
# Integration with existing services
class GPUStackIntegrationService:
    def __init__(self, monitoring_service, graph_service, knowledge_service):
        self.monitoring_service = monitoring_service
        self.graph_service = graph_service
        self.knowledge_service = knowledge_service
        
    async def process_document_with_tracking(self, document_data, user_id, project_id):
        """Process document with all integration points"""
        # Step 1: Process document through graph service
        doc_id = await self.graph_service.create_document(document_data)
        
        # Step 2: Record usage in monitoring system
        usage_record = UsageRecord(
            user_id=user_id,
            team_id=self._get_user_team_id(user_id),
            model_name="document-processing",
            input_tokens=len(document_data['content']),
            output_tokens=0,
            total_tokens=len(document_data['content']),
            request_duration_ms=100,
            api_key="system-key",
            status_code=200
        )
        await self.monitoring_service.record_usage(usage_record)
        
        # Step 3: Associate with project in knowledge system
        relation = ProjectKnowledgeRelation(
            project_id=project_id,
            knowledge_item_id=doc_id,
            relevance_score=0.95,
            relationship_type="related"
        )
        await self.knowledge_service.associate_project_knowledge(relation)
        
        return doc_id
    
    def _get_user_team_id(self, user_id):
        """Get team ID for user (mock implementation)"""
        # In real system, query user database
        return "team-legal"
```

### 3. Institutional Knowledge Integration

#### Project Overlap Detection
The institutional knowledge management system integrates with the monitoring system for insights:

1. **Overlap Detection**:
   - Automatically detect project overlaps based on knowledge items
   - Use monitoring data to identify projects with similar usage patterns
   - Create alerts when overlaps are detected

2. **Knowledge Sharing**:
   - Recommend relevant knowledge to developers working on overlapping projects
   - Provide insights to prevent duplication of efforts
   - Track knowledge usage for improvement

3. **Cross-System Notifications**:
   - Alert developers when their project overlaps with others
   - Notify legal teams about potentially contradictory documents
   - Provide visibility to management about knowledge sharing effectiveness

## Unified Dashboard Integration

### Grafana Dashboard Components

#### 1. User Activity Dashboard
```yaml
# Dashboard configuration for user monitoring
title: "User Activity and Resource Usage"
panels:
  - name: "Team Resource Usage"
    type: graph
    targets:
      - query: "sum by(team_id) (rate(usage_tokens_total[5m]))"
        legend: "{{team_id}}"
  - name: "User Activity by Model"
    type: table
    targets:
      - query: "sum by(user_id, model_name) (rate(usage_tokens_total[5m]))"
```

#### 2. Document Relationship Dashboard
```yaml
# Dashboard for document relationships  
title: "Document Relationships and Contradictions"
panels:
  - name: "Document Network Analysis"
    type: graph
    targets:
      - query: "count(document_relationships)"
  - name: "Contradiction Detection Alerts"
    type: alert
    targets:
      - query: "sum(contradiction_alerts)"
```

#### 3. Project Overlap Dashboard
```yaml
# Dashboard for project overlaps and knowledge sharing
title: "Project Overlaps and Knowledge Sharing"
panels:
  - name: "Active Project Overlaps"
    type: table
    targets:
      - query: "count(project_overlaps{status='active'})"
  - name: "Knowledge Item Distribution"
    type: pie
    targets:
      - query: "count(knowledge_items) by(category)"
```

## Security and Compliance Integration

### 1. Role-Based Access Control
All systems integrate with the existing IAM Identity Center/OAuth2 setup:

```yaml
# RBAC Configuration for all services
roles:
  - name: legal-analyst
    permissions:
      - read_documents
      - read_contradictions
      - view_document_network
      - write_document_relations
  - name: security-analyst  
    permissions:
      - read_security_logs
      - view_security_correlations
      - view_document_security_links
  - name: developer
    permissions:
      - read_relevant_knowledge
      - view_project_overlaps
      - access_document_relationships
```

### 2. Audit Logging
All systems maintain audit logs that can be aggregated for compliance reporting:

```sql
-- Audit log table that all services can use
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    user_id UUID,
    action VARCHAR(100),
    resource_type VARCHAR(50),
    resource_id UUID,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- Example audit trails
INSERT INTO audit_logs (id, user_id, action, resource_type, resource_id, metadata) 
VALUES (uuid_generate_v4(), 'user-123', 'document_created', 'document', 'doc-456', 
        '{"source": "graph_service", "tags": ["legal", "contract"]}');
```

## Data Flow Between Systems

### 1. Monitoring → Knowledge Management
- Team resource usage data triggers project overlap analysis
- High-usage projects are flagged for potential knowledge sharing opportunities
- Cost allocation data helps prioritize knowledge management efforts

### 2. Document Management → Knowledge Management  
- Document relationship detection triggers project overlap detection
- Contradiction alerts are sent to knowledge management system
- Document categories help determine project knowledge relevance

### 3. Knowledge Management → Monitoring
- Project overlap notifications send alerts to monitoring system
- Knowledge access patterns indicate user engagement with system
- Project statistics inform resource allocation decisions

## Deployment Configuration

### 1. Kubernetes Deployment Integration

```yaml
# Monitoring Service Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: monitoring-service
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: monitoring-service
        image: your-registry/monitoring-service:latest
        env:
        - name: REDIS_HOST
          value: "redis-service"
        - name: DB_HOST
          value: "postgres-service"
        - name: GRAPH_URI  
          value: "bolt://neo4j-service:7687"
        - name: ES_HOSTS
          value: '["elasticsearch-service:9200"]'
```

### 2. Service Communication Protocol

All services communicate through standardized REST endpoints or GraphQL queries:

```python
# Service communication example
class UnifiedAPI:
    async def get_user_dashboard_data(self, user_id):
        """Get comprehensive dashboard data for user"""
        # Get user activity from monitoring service
        user_activity = await self.monitoring_service.get_user_activity(user_id)
        
        # Get relevant knowledge from knowledge service  
        user_knowledge = await self.knowledge_service.get_user_relevant_knowledge(user_id)
        
        # Get document relationships from graph service
        doc_relationships = await self.graph_service.find_documents_by_semantic_search(
            f"user {user_id} recent work", 5
        )
        
        return {
            'user_activity': user_activity,
            'relevant_knowledge': user_knowledge,
            'document_relationships': doc_relationships
        }
```

## Performance Monitoring and Alerting

### 1. System Health Monitoring
- All services expose Prometheus metrics
- Kubernetes readiness/liveness probes ensure service health
- Aggregate monitoring dashboard for all systems

### 2. Performance Indicators
- API response times < 500ms for 95% of requests
- Graph query response times < 200ms for 95% of queries  
- Database query optimization for frequent operations

### 3. Alerting Configuration
```yaml
# Alert rules for integrated system
rules:
  - alert: HighUsageByTeam
    expr: sum by(team_id) (rate(usage_tokens_total[5m])) > 1000000
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High usage detected for team {{ $labels.team_id }}"
      
  - alert: DocumentContradiction
    expr: sum(contradiction_alerts) > 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Document contradictions detected"
```

## Operational Procedures

### 1. Daily Operations
- Monitor API response times and error rates
- Review usage reports for cost allocation
- Check document contradiction detection
- Validate project overlap detection accuracy

### 2. Weekly Operations  
- Generate usage analytics for legal/finance teams
- Review project overlap recommendations
- Analyze knowledge sharing effectiveness
- Update document relationship models based on new data

### 3. Monthly Operations
- Generate comprehensive usage reports
- Conduct compliance audit of monitoring records
- Review system performance metrics
- Update security correlation rules

## Integration Testing

### 1. End-to-End Test Scenarios
1. **User Usage Flow**: 
   - User makes request through API Gateway
   - Usage recorded in monitoring service
   - Data available in knowledge management system

2. **Document Processing Flow**:
   - Document ingested by graph service  
   - Relationships detected and stored
   - Knowledge tracking updated

3. **Project Overlap Flow**:
   - Project knowledge items added
   - Overlap detection triggered
   - Notifications sent to relevant stakeholders

### 2. Integration Test Configuration
```yaml
# Test configuration for integrated system
test_scenarios:
  - name: user_monitoring_integration
    steps:
      - make_api_call_to_gateway
      - verify_usage_recorded_in_db
      - validate_metrics_in_prometheus
      
  - name: document_management_integration  
    steps:
      - ingest_document
      - verify_graph_nodes_created
      - check_relationships_stored
      - validate_contradiction_detection
```

This integration provides a unified, cohesive ecosystem that enables:
- Comprehensive user usage tracking for financial and compliance teams
- Robust document relationship management with contradiction detection  
- Effective institutional knowledge management to prevent project overlaps
- Seamless cross-system communication and data flow
- Unified monitoring and alerting across all components

All systems leverage the existing GPU-Stack infrastructure while adding the required functionality to address the three main concerns: user monitoring, feedback/RAG loops, and institutional knowledge management.