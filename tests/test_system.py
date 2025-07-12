"""
Test suite for YouTube Content Automation System
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
import os
import sys

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.main import app
from src.models import InputData, WorkflowConfig
from src.ai_service import AIContentGenerator
from src.image_service import ImageGenerator
from src.workflow_engine import WorkflowEngine

client = TestClient(app)


class TestAPI:
    """Test API endpoints"""
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data
    
    def test_home_page(self):
        """Test home page loads"""
        response = client.get("/")
        assert response.status_code == 200
        assert "YouTube Content Automation" in response.text
    
    def test_dashboard_page(self):
        """Test dashboard page loads"""
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "Dashboard" in response.text
    
    def test_get_config(self):
        """Test get configuration endpoint"""
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "auto_generate_content" in data
        assert "openai_model" in data
    
    def test_get_packages(self):
        """Test get packages endpoint"""
        response = client.get("/api/packages")
        assert response.status_code == 200
        data = response.json()
        assert "packages" in data
        assert "total" in data


class TestModels:
    """Test data models"""
    
    def test_input_data_creation(self):
        """Test InputData model creation"""
        input_data = InputData(
            channel_name="Test Channel",
            channel_description="Test Description"
        )
        assert input_data.channel_name == "Test Channel"
        assert input_data.channel_description == "Test Description"
        assert input_data.created_by == "Anh Hà Tiến"
    
    def test_workflow_config(self):
        """Test WorkflowConfig model"""
        config = WorkflowConfig()
        assert config.auto_generate_content == True
        assert config.auto_generate_images == True
        assert config.openai_model == "gpt-4"


class TestAIService:
    """Test AI service functionality"""
    
    @patch('openai.OpenAI')
    def test_ai_content_generator_init(self, mock_openai):
        """Test AI content generator initialization"""
        ai_gen = AIContentGenerator()
        assert ai_gen.client is not None
        assert ai_gen.config is not None
    
    def test_create_content_generation_prompt(self):
        """Test prompt creation"""
        ai_gen = AIContentGenerator()
        input_data = InputData(
            channel_name="Tech Channel",
            channel_description="Technology reviews"
        )
        
        prompt = ai_gen._create_content_generation_prompt(input_data)
        assert "Tech Channel" in prompt
        assert "Technology reviews" in prompt
        assert "JSON" in prompt


class TestImageService:
    """Test image generation service"""
    
    def test_image_generator_init(self):
        """Test image generator initialization"""
        img_gen = ImageGenerator()
        assert img_gen.config is not None
        assert img_gen.storage_path is not None


class TestWorkflowEngine:
    """Test workflow engine"""
    
    def test_workflow_engine_init(self):
        """Test workflow engine initialization"""
        engine = WorkflowEngine()
        assert engine.config is not None
        assert engine.active_packages == {}
    
    @pytest.mark.asyncio
    async def test_create_content_package(self):
        """Test content package creation"""
        engine = WorkflowEngine()
        input_data = InputData(
            channel_name="Test Channel",
            channel_description="Test Description"
        )
        
        package = await engine.create_content_package(input_data)
        assert package.id is not None
        assert package.input_data.channel_name == "Test Channel"
        assert package.status.value == "pending"


class TestIntegration:
    """Integration tests"""
    
    @pytest.mark.asyncio
    async def test_create_content_api_mock(self):
        """Test create content API with mocked services"""
        
        # Mock data
        form_data = {
            "channel_name": "Test Channel",
            "channel_description": "Test Description",
            "additional_context": "Test context"
        }
        
        # Test the API endpoint (will run in background)
        response = client.post("/api/create-content", data=form_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "message" in data


class TestUtils:
    """Test utility functions"""
    
    def test_environment_variables(self):
        """Test that required environment variables are accessible"""
        from config.settings import settings
        
        # These should be accessible even if not set (will use defaults)
        assert hasattr(settings, 'app_host')
        assert hasattr(settings, 'app_port')
        assert hasattr(settings, 'debug')


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 