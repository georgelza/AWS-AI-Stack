# User Usage Monitoring System for GPU-Stack

## Overview

This document outlines the implementation of a comprehensive user usage monitoring system for the GPU-Stack platform. The system will track user resource allocation, token usage, model selection, and provide detailed analytics for legal/finance teams.

## Architecture

The monitoring system integrates with the existing GPU-Stack architecture through the LiteLLM proxy and API Gateway components.

### Components

1. **Monitoring Service** - Core service that collects and processes usage data
2. **Data Store** - PostgreSQL for structured data, Redis for caching
3. **API Gateway Integration** - Collects authentication data and API metrics
4. **Analytics Engine** - Processes usage data for reporting
5. **Dashboard** - Grafana dashboards for real-time monitoring

## Implementation Plan

### 1. Data Collection Points

#### LiteLLM Proxy Integration
The monitoring service will integrate with LiteLLM to collect:
- User identification (virtual key mapping)
- Token usage (input/output)
- Model selection
- Request duration
- Error rates

#### API Gateway Integration
The system will collect data from Axway API Gateway:
- User authentication details
- Rate limiting events
- Request timestamps
- IP addresses

### 2. Database Schema

```sql
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
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    api_key VARCHAR(255),
    status_code INTEGER
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3. Monitoring Service Implementation (Python)

```python
# monitor_service.py
import asyncio
import logging
import time
from typing import Dict, Any
from dataclasses import dataclass
from datetime import datetime
import uuid
import redis
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel

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
        
    async def record_usage(self, record: UsageRecord):
        """Record user usage in database"""
        try:
            # Generate unique ID for this record
            record_id = str(uuid.uuid4())
            
            # Insert usage record
            self.cursor.execute("""
                INSERT INTO usage_logs (id, user_id, team_id, model_name, 
                                       input_tokens, output_tokens, total_tokens,
                                       request_duration_ms, api_key, status_code)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                record_id, record.user_id, record.team_id, record.model_name,
                record.input_tokens, record.output_tokens, record.total_tokens,
                record.request_duration_ms, record.api_key, record.status_code
            ))
            
            # Record resource allocation if needed (for GPU usage)
            # This would be called when pod is scheduled
            
            # Update summary tables
            self._update_token_usage_summary(record.team_id, record)
            
            self.db_connection.commit()
            
            logger.info(f"Recorded usage for user {record.user_id}")
            
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
                    unique_users = CASE WHEN unique_users IS NULL THEN 1 ELSE unique_users + 1 END
                WHERE team_id = %s AND date = %s
            """, (record.input_tokens, record.output_tokens, team_id, today))
        else:
            # Create new summary
            self.cursor.execute("""
                INSERT INTO token_usage_summary (id, team_id, date, total_input_tokens, 
                                               total_output_tokens, total_requests, unique_users)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                str(uuid.uuid4()), team_id, today, record.input_tokens,
                record.output_tokens, 1, 1
            ))
            
    async def get_team_usage_report(self, team_id: str, start_date: str, end_date: str):
        """Generate usage report for a specific team"""
        self.cursor.execute("""
            SELECT 
                DATE(timestamp) as date,
                COUNT(*) as request_count,
                SUM(input_tokens) as total_input_tokens,
                SUM(output_tokens) as total_output_tokens,
                AVG(request_duration_ms) as avg_duration
            FROM usage_logs 
            WHERE team_id = %s AND timestamp BETWEEN %s AND %s
            GROUP BY DATE(timestamp)
            ORDER BY date
        """, (team_id, start_date, end_date))
        
        return self.cursor.fetchall()
        
    async def get_user_activity(self, user_id: str, limit: int = 100):
        """Get recent activity for a user"""
        self.cursor.execute("""
            SELECT * FROM usage_logs 
            WHERE user_id = %s 
            ORDER BY timestamp DESC 
            LIMIT %s
        """, (user_id, limit))
        
        return self.cursor.fetchall()

# API Endpoints
app = FastAPI(title="GPU Stack Monitoring API")

# Dependency injection for monitoring service
def get_monitoring_service():
    return MonitoringService()

@app.post("/usage")
async def record_usage(record: UsageRecord, monitor: MonitoringService = Depends(get_monitoring_service)):
    """Record usage data from LiteLLM or API Gateway"""
    try:
        await monitor.record_usage(record)
        return {"status": "success", "message": "Usage recorded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/team/{team_id}/report")
async def team_report(team_id: str, start_date: str, end_date: str, 
                     monitor: MonitoringService = Depends(get_monitoring_service)):
    """Get usage report for a team"""
    try:
        report = await monitor.get_team_usage_report(team_id, start_date, end_date)
        return {"team_id": team_id, "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user/{user_id}/activity")
async def user_activity(user_id: str, limit: int = 100,
                       monitor: MonitoringService = Depends(get_monitoring_service)):
    """Get recent activity for a user"""
    try:
        activity = await monitor.get_user_activity(user_id, limit)
        return {"user_id": user_id, "activity": activity}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 4. Integration with Existing Infrastructure

#### LiteLLM Configuration
Add monitoring to LiteLLM configuration:
```yaml
# Example LiteLLM config.yaml
model_list:
  - model_name: qwen-coder
    litellm_params:
      model: openai/qwen2.5-coder-32b
      api_base: http://vllm-qwen.internal.eks.local:8000/v1
      api_key: "vllm-internal-key"
      # Add monitoring endpoint
      callback_url: "http://monitoring-service:8000/usage"

router_settings:
  routing_strategy: usage-based-routing-v2
  # Add logging and monitoring hooks
  custom_logging: true
```

### 5. Dashboard Components

#### Grafana Dashboards
1. **Team Resource Usage Dashboard**
   - Token usage per team over time
   - GPU utilization by team
   - Cost allocation by department

2. **User Activity Dashboard**
   - Individual user token consumption
   - Model selection patterns
   - Error rates by user

3. **System Performance Dashboard**
   - API response times
   - Resource utilization
   - Error rates and service health

## Security and Compliance

### Access Control
- RBAC for monitoring data access
- Audit logging for all monitoring activities
- Data encryption at rest and in transit

### Data Retention
- Usage logs retained for 12 months
- Audit logs retained for 24 months
- PII data de-identified or encrypted

## Deployment Instructions

### 1. Database Setup
```bash
# Create PostgreSQL database
createdb ai_platform

# Apply schema
psql -d ai_platform -f monitoring-schema.sql
```

### 2. Service Deployment
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
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
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
```

## Monitoring Metrics

### Key Metrics to Track
1. **Token Usage**
   - Input tokens per team/user/day
   - Output tokens per team/user/day
   - Total token consumption trends

2. **Model Performance**
   - Average request duration by model
   - Error rate by model
   - Token efficiency

3. **Resource Utilization**
   - GPU usage by user/team
   - Memory allocation
   - CPU usage

### Alerting Rules
1. **High Usage Alerts**
   - Token usage exceeds 80% of limit
   - Unexpected model selection spikes

2. **System Health Alerts**
   - Response time > 500ms
   - Error rate > 5%
   - Resource utilization > 90%

This implementation provides comprehensive user usage monitoring that enables legal/finance teams to track usage patterns, generate cost reports, and maintain compliance with usage tracking requirements.