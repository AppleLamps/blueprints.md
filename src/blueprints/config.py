"""Configuration management for blueprints.md."""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class BlueprintsConfig(BaseSettings):
    """Configuration settings for blueprints.md."""
    
    # API Configuration
    openrouter_api_key: Optional[str] = Field(None, env="OPENROUTER_API_KEY")
    default_model: str = Field("anthropic/claude-3.5-sonnet", env="BLUEPRINTS_MODEL")
    
    # Generation Settings
    default_language: str = Field("python", env="BLUEPRINTS_LANGUAGE")
    max_tokens: int = Field(4000, env="BLUEPRINTS_MAX_TOKENS")
    temperature: float = Field(0.0, env="BLUEPRINTS_TEMPERATURE")
    
    # File Settings
    blueprint_extensions: list[str] = Field(default_factory=lambda: [".md"])
    
    class Config:
        env_prefix = "BLUEPRINTS_"
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @classmethod
    def from_env(cls) -> "BlueprintsConfig":
        """Create config from environment variables."""
        return cls()
    
    def get_api_key(self) -> Optional[str]:
        """Get the API key, checking multiple sources."""
        # Check explicit config
        if self.openrouter_api_key:
            return self.openrouter_api_key
        
        # Check environment variable
        return os.environ.get("OPENROUTER_API_KEY")


# Global config instance
config = BlueprintsConfig.from_env()