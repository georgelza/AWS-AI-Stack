# Institutional Knowledge Management System

## Overview

This document outlines the implementation of an institutional knowledge management system that helps track overlapping projects and provides institutional knowledge to development teams. The system integrates with the existing GPU-Stack architecture to maintain cross-project knowledge sharing and prevent duplication of efforts.

## Architecture

The system uses a structured approach combining document management, project tracking, and knowledge sharing features to maintain institutional knowledge while supporting overlapping development projects.

### Components

1. **Knowledge Base Service** - Central repository for institutional knowledge
2. **Project Management Integration** - Tracks project overlaps and dependencies
3. **Knowledge Sharing Engine** - Recommends relevant knowledge to developers
4. **Cross-Project Analysis** - Identifies overlapping projects and knowledge areas
5. **Notification System** - Alerts developers about relevant knowledge
6. **Analytics Dashboard** - Tracks knowledge usage and project overlap

## Implementation Plan

### 1. Knowledge Base Data Model

#### Core Entities

```sql
-- Knowledge base items
CREATE TABLE knowledge_items (
    id UUID PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    content TEXT,
    category VARCHAR(100),
    created_by UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active',
    tags TEXT[],  -- Array of tags for categorization
    metadata JSONB  -- Additional structured metadata
);

-- Project information
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
    relationship_type VARCHAR(50),  -- 'related', 'overlaps', 'dependency', etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cross-project overlaps
CREATE TABLE project_overlaps (
    id UUID PRIMARY KEY,
    project1_id UUID REFERENCES projects(id),
    project2_id UUID REFERENCES projects(id),
    overlap_type VARCHAR(50),  -- 'code', 'architecture', 'documentation', etc.
    overlap_details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User knowledge access
CREATE TABLE user_knowledge_access (
    id UUID PRIMARY KEY,
    user_id UUID,
    knowledge_item_id UUID REFERENCES knowledge_items(id),
    access_type VARCHAR(20),  -- 'view', 'edit', 'comment'
    access_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. Knowledge Management Service (Python)

```python
# knowledge_service.py
import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

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
        
    async def create_knowledge_item(self, knowledge_item: KnowledgeItem) -> str:
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
            
    async def create_project(self, project: Project) -> str:
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
            
    async def associate_project_knowledge(self, relation: ProjectKnowledgeRelation):
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
            
    async def find_overlapping_projects(self, project_id: str) -> List[Dict]:
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
            
    async def find_related_knowledge(self, project_id: str, limit: int = 10) -> List[Dict]:
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
            
    async def get_user_relevant_knowledge(self, user_id: str, project_id: str = None, 
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
            
    async def create_project_overlap(self, project1_id: str, project2_id: str, 
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
            
    async def get_project_knowledge_statistics(self, project_id: str) -> Dict:
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

# API Endpoints
app = FastAPI(title="Institutional Knowledge Management API")

# Dependency injection
def get_knowledge_service():
    return KnowledgeManagementService()

@app.post("/knowledge")
async def create_knowledge_item(item: KnowledgeItem, 
                               knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Create a new knowledge item"""
    try:
        item_id = await knowledge_service.create_knowledge_item(item)
        return {"id": item_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/projects")
async def create_project(project: Project, 
                        knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Create a new project"""
    try:
        project_id = await knowledge_service.create_project(project)
        return {"id": project_id, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/project/{project_id}/knowledge")
async def associate_knowledge(project_id: str, relation: ProjectKnowledgeRelation,
                             knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Associate knowledge with a project"""
    try:
        relation.project_id = project_id  # Ensure project ID is set
        await knowledge_service.associate_project_knowledge(relation)
        return {"status": "associated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/project/{project_id}/overlaps")
async def get_project_overlaps(project_id: str, 
                              knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Find projects that overlap with the given project"""
    try:
        overlaps = await knowledge_service.find_overlapping_projects(project_id)
        return {"overlaps": overlaps}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/project/{project_id}/related-knowledge")
async def get_project_related_knowledge(project_id: str, limit: int = 10,
                                       knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Get knowledge items related to a project"""
    try:
        related = await knowledge_service.find_related_knowledge(project_id, limit)
        return {"related_knowledge": related}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user/{user_id}/relevant-knowledge")
async def get_user_relevant_knowledge(user_id: str, project_id: Optional[str] = None,
                                     limit: int = 20,
                                     knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Get knowledge relevant to a user"""
    try:
        relevant = await knowledge_service.get_user_relevant_knowledge(user_id, project_id, limit)
        return {"relevant_knowledge": relevant}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/project/{project1_id}/overlap/{project2_id}")
async def create_overlap(project1_id: str, project2_id: str,
                        overlap_type: str, overlap_details: str,
                        knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Create a relationship between two projects indicating overlap"""
    try:
        await knowledge_service.create_project_overlap(project1_id, project2_id, 
                                                     overlap_type, overlap_details)
        return {"status": "overlap created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/project/{project_id}/statistics")
async def get_project_statistics(project_id: str,
                                knowledge_service: KnowledgeManagementService = Depends(get_knowledge_service)):
    """Get knowledge statistics for a project"""
    try:
        stats = await knowledge_service.get_project_knowledge_statistics(project_id)
        return {"statistics": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 3. Project Overlap Detection System

```python
# overlap_detection.py
import asyncio
import logging
from typing import Dict, List, Set
from datetime import datetime
import re
from collections import defaultdict

logger = logging.getLogger(__name__)

class OverlapDetectionService:
    def __init__(self, knowledge_service):
        self.knowledge_service = knowledge_service
        
    async def detect_project_overlaps(self, project_ids: List[str] = None):
        """Detect overlaps between projects based on knowledge items"""
        try:
            if not project_ids:
                # Get all active projects
                # This would query the projects table
                project_ids = self._get_active_projects()
            
            # For each pair of projects, check for overlaps
            project_overlaps = []
            
            for i, project1_id in enumerate(project_ids):
                for project2_id in project_ids[i+1:]:
                    overlap = await self._check_project_overlap(project1_id, project2_id)
                    if overlap:
                        project_overlaps.append(overlap)
                        
            return project_overlaps
            
        except Exception as e:
            logger.error(f"Error detecting project overlaps: {e}")
            raise
            
    async def _check_project_overlap(self, project1_id: str, project2_id: str) -> Optional[Dict]:
        """Check if two projects overlap based on their related knowledge items"""
        try:
            # Get knowledge items for both projects
            project1_knowledge = await self.knowledge_service.find_related_knowledge(project1_id, 50)
            project2_knowledge = await self.knowledge_service.find_related_knowledge(project2_id, 50)
            
            # Convert to sets of knowledge item IDs for comparison
            project1_knowledge_ids = {item['id'] for item in project1_knowledge}
            project2_knowledge_ids = {item['id'] for item in project2_knowledge}
            
            # Find common knowledge items
            common_items = project1_knowledge_ids.intersection(project2_knowledge_ids)
            
            if common_items:
                # Determine overlap type based on knowledge categories
                overlap_type = self._determine_overlap_type(
                    project1_knowledge, project2_knowledge, common_items
                )
                
                return {
                    'project1_id': project1_id,
                    'project2_id': project2_id,
                    'overlap_type': overlap_type,
                    'common_knowledge_count': len(common_items),
                    'common_knowledge_ids': list(common_items),
                    'detected_at': datetime.now().isoformat()
                }
                
            return None
            
        except Exception as e:
            logger.error(f"Error checking project overlap: {e}")
            return None
            
    def _determine_overlap_type(self, project1_knowledge: List[Dict], 
                              project2_knowledge: List[Dict], 
                              common_items: Set[str]) -> str:
        """Determine the type of overlap based on knowledge categories"""
        # Get categories of common knowledge items
        common_categories = set()
        for item in project1_knowledge:
            if item['id'] in common_items and item['category']:
                common_categories.add(item['category'])
                
        # If no categories, or only one category, use content matching
        if not common_categories:
            # Apply text similarity or content analysis
            return "knowledge"
            
        # Determine overlap type based on main categories
        if "architecture" in common_categories or "design" in common_categories:
            return "architecture"
        elif "security" in common_categories or "compliance" in common_categories:
            return "security"
        elif "documentation" in common_categories or "guidelines" in common_categories:
            return "documentation"
        else:
            return "knowledge"
            
    async def detect_keywords_overlap(self, project1_id: str, project2_id: str) -> Dict:
        """Detect overlap based on keyword matching in knowledge content"""
        try:
            # Get knowledge content for both projects
            project1_knowledge = await self.knowledge_service.find_related_knowledge(project1_id, 100)
            project2_knowledge = await self.knowledge_service.find_related_knowledge(project2_id, 100)
            
            # Extract keywords from content
            project1_keywords = self._extract_keywords([item['content'] for item in project1_knowledge])
            project2_keywords = self._extract_keywords([item['content'] for item in project2_knowledge])
            
            # Find common keywords
            common_keywords = project1_keywords.intersection(project2_keywords)
            
            overlap_details = {
                'common_keywords': list(common_keywords),
                'keyword_similarity': len(common_keywords) / max(len(project1_keywords), len(project2_keywords), 1),
                'keyword_count': len(common_keywords)
            }
            
            return overlap_details
            
        except Exception as e:
            logger.error(f"Error detecting keyword overlap: {e}")
            return {}

    def _extract_keywords(self, content_list: List[str]) -> Set[str]:
        """Extract keywords from content using regex patterns"""
        keywords = set()
        text = " ".join(content_list).lower()
        
        # Common patterns for technical terms
        patterns = [
            r'\b[a-zA-Z_][a-zA-Z0-9_]*\b',  # Variable names
            r'\b(?:class|function|method|interface|module)\s+\w+\b',
            r'\b(?:import|from|as|def|class|if|else|try|except|for|while)\b',
            r'\b(?:[A-Z][a-zA-Z0-9]+(?:[A-Z][a-zA-Z0-9]*)*)\b'  # PascalCase
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            keywords.update(matches)
            
        # Remove common words
        common_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were'}
        keywords = keywords - common_words
        
        return keywords

    def _get_active_projects(self) -> List[str]:
        """Get list of active projects (mock implementation)"""
        # In real implementation, this would query the projects table
        return ["project1", "project2", "project3"]  # Placeholder
```

### 4. Notification and Alerting System

```python
# notification_service.py
import asyncio
import logging
from typing import Dict, List
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self, smtp_server: str, smtp_port: int, email_user: str, email_password: str):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.email_user = email_user
        self.email_password = email_password
        
    async def send_project_overlap_alert(self, recipient_email: str, project_names: List[str], 
                                       overlap_details: Dict, knowledge_items: List[Dict]):
        """Send notification about project overlaps"""
        try:
            # Create email content
            message = MIMEMultipart()
            message["From"] = self.email_user
            message["To"] = recipient_email
            message["Subject"] = f"Project Overlap Alert: {', '.join(project_names)}"
            
            # Email body
            body = f"""
            Project Overlap Alert
            
            The following projects have been detected as having overlapping knowledge:
            - {project_names[0]}
            - {project_names[1]}
            
            Overlap Details:
            Type: {overlap_details.get('overlap_type', 'Unknown')}
            Common Knowledge Items: {overlap_details.get('common_knowledge_count', 0)}
            
            Related Knowledge Items:
            """
            
            for item in knowledge_items[:5]:  # Show first 5 items
                body += f"""
                - {item.get('title', 'Untitled')}
                - Category: {item.get('category', 'Unknown')}
                """
                
            body += "\n\nPlease review and coordinate to avoid duplication.\n\nBest regards,\nPlatform Team"
            
            message.attach(MIMEText(body, "plain"))
            
            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.email_user, self.email_password)
            server.send_message(message)
            server.quit()
            
            logger.info(f"Sent overlap alert to {recipient_email}")
            
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            raise
            
    async def send_knowledge_recommendation(self, recipient_email: str, 
                                          knowledge_items: List[Dict], 
                                          project_name: str):
        """Send recommendation for relevant knowledge to a developer"""
        try:
            message = MIMEMultipart()
            message["From"] = self.email_user
            message["To"] = recipient_email
            message["Subject"] = f"Knowledge Recommendation for {project_name}"
            
            body = f"""
            Knowledge Recommendation
            
            Based on your current work on {project_name}, you might find the following resources helpful:
            
            """
            
            for item in knowledge_items[:3]:  # Show top 3 items
                body += f"""
                - {item.get('title', 'Untitled')}
                - Category: {item.get('category', 'Unknown')}
                - Relevance: {item.get('relevance_score', 0):.2f}
                """
                
            body += "\n\nThese recommendations are based on project overlaps and common knowledge patterns.\n\nBest regards,\nPlatform Team"
            
            message.attach(MIMEText(body, "plain"))
            
            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.email_user, self.email_password)
            server.send_message(message)
            server.quit()
            
            logger.info(f"Sent knowledge recommendation to {recipient_email}")
            
        except Exception as e:
            logger.error(f"Error sending recommendation: {e}")
            raise

# Integration with knowledge service
class InstitutionalKnowledgeSystem:
    def __init__(self, knowledge_service, overlap_service, notification_service):
        self.knowledge_service = knowledge_service
        self.overlap_service = overlap_service
        self.notification_service = notification_service
        
    async def handle_new_knowledge_creation(self, knowledge_item_id: str, 
                                          project_id: str, user_id: str):
        """Handle when new knowledge is created and notify relevant parties"""
        try:
            # Find projects that might benefit from this knowledge
            relevant_projects = await self._find_relevant_projects(knowledge_item_id)
            
            # Send recommendations to developers working on relevant projects
            for project_id in relevant_projects:
                # Send knowledge recommendations
                relevant_knowledge = await self.knowledge_service.find_related_knowledge(project_id, 5)
                if relevant_knowledge:
                    # Get project owner or team members
                    # (In real implementation, this would query user/project data)
                    recipient_email = "developer@example.com"  # Placeholder
                    await self.notification_service.send_knowledge_recommendation(
                        recipient_email, relevant_knowledge, "Project Name"
                    )
                    
        except Exception as e:
            logger.error(f"Error handling new knowledge creation: {e}")
            raise
            
    async def _find_relevant_projects(self, knowledge_item_id: str) -> List[str]:
        """Find projects that might be relevant to this knowledge item"""
        # In implementation, this would query based on tags, categories, etc.
        return []  # Placeholder
```

### 5. Analytics Dashboard

```python
# analytics_service.py
import asyncio
import logging
from typing import Dict, List, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AnalyticsService:
    def __init__(self, knowledge_service):
        self.knowledge_service = knowledge_service
        
    async def get_institutional_knowledge_stats(self) -> Dict:
        """Get overall statistics about institutional knowledge"""
        try:
            # Get total knowledge items
            total_knowledge = await self._get_total_knowledge_items()
            
            # Get knowledge by category
            knowledge_by_category = await self._get_knowledge_by_category()
            
            # Get knowledge growth over time
            knowledge_growth = await self._get_knowledge_growth()
            
            # Get overlap statistics
            overlap_stats = await self._get_overlap_statistics()
            
            return {
                'total_knowledge_items': total_knowledge,
                'knowledge_by_category': knowledge_by_category,
                'knowledge_growth': knowledge_growth,
                'overlap_statistics': overlap_stats,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting knowledge stats: {e}")
            raise
            
    async def _get_total_knowledge_items(self) -> int:
        """Get total number of knowledge items"""
        # Implementation would query knowledge_items table
        return 500  # Placeholder
        
    async def _get_knowledge_by_category(self) -> Dict:
        """Get knowledge items by category"""
        # Implementation would query knowledge_items table
        return {
            'architecture': 120,
            'security': 85,
            'development': 200,
            'documentation': 95,
            'process': 100
        }
        
    async def _get_knowledge_growth(self) -> List[Dict]:
        """Get knowledge growth over time"""
        # Implementation would query knowledge_items with timestamps
        return [
            {'date': '2024-01-01', 'count': 100},
            {'date': '2024-02-01', 'count': 150},
            {'date': '2024-03-01', 'count': 200},
            {'date': '2024-04-01', 'count': 300},
            {'date': '2024-05-01', 'count': 400},
            {'date': '2024-06-01', 'count': 500}
        ]
        
    async def _get_overlap_statistics(self) -> Dict:
        """Get project overlap statistics"""
        # Implementation would query project_overlaps table
        return {
            'total_overlaps': 15,
            'overlap_types': {
                'architecture': 5,
                'knowledge': 7,
                'security': 3
            },
            'active_projects_with_overlaps': 8
        }
```

## Integration with Existing Systems

### 1. Monitoring Integration
```yaml
# Add to monitoring-service
- name: "knowledge_usage"
  url: "http://knowledge-service:8000/analytics/stats"
  events: ["daily"]
```

### 2. Notification Integration
Add to project team members or developer workflow:
```yaml
# Email notification when project overlaps detected
- when: project_overlap_detected
- for_each: project_team_members
- send: knowledge_overlap_notification
```

## Deployment Instructions

### 1. Database Setup
```sql
-- Create tables (from earlier sections)
-- Apply schema to PostgreSQL database

-- Create indexes for performance
CREATE INDEX idx_projects_status ON projects(status);
CREATE INDEX idx_knowledge_items_status ON knowledge_items(status);
CREATE INDEX idx_project_knowledge_project ON project_knowledge(project_id);
CREATE INDEX idx_project_knowledge_knowledge ON project_knowledge(knowledge_item_id);
```

### 2. Service Deployment
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
        - containerPort: 8000
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
    targetPort: 8000
```

## Security and Compliance

### Access Control
- Role-based access to knowledge items
- Audit logging for all knowledge access
- Data encryption at rest and in transit
- Compliance with data protection regulations

### Data Retention
- Knowledge items retained for 5 years
- Audit logs retained for 7 years
- Regular security reviews and access audits

## Monitoring and Alerting

### Key Metrics to Track
1. **Knowledge Growth**
   - Number of new knowledge items per day
   - Knowledge item categories distribution
   - Knowledge contributor statistics

2. **Project Overlap**
   - Project overlap detection rate
   - Overlap resolution time
   - Overlap prevention success rate

3. **User Engagement**
   - Knowledge access frequency
   - Knowledge sharing activities
   - User feedback on knowledge quality

### Alerting Rules
1. **High Overlap Detection**
   - When 3 or more projects show overlaps
   - When new overlapping knowledge is identified

2. **Knowledge Access**
   - When critical knowledge is accessed
   - When knowledge access patterns change significantly

This implementation provides a comprehensive institutional knowledge management system that helps track overlapping projects, enables knowledge sharing between teams, and provides insights to prevent duplication of efforts while maintaining comprehensive institutional knowledge within the organization.