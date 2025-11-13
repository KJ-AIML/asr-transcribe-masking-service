from typing import Optional, Dict, Any
from src.agents.schemas.types import (
    Agent1Output, 
    SelfCheckerResult, 
    SensitiveDataDetectorOutput, 
    PIIWorkerOutput
)
from src.models.langchain_model_loader import LangchainModelLoader
from src.config.logs_config import get_logger

logger = get_logger(__name__)

class AgentManager:
    def __init__(self, model_loader: Optional[LangchainModelLoader] = None):
        self.model_loader = model_loader or LangchainModelLoader()
        self._model = None
        self._agents: Dict[str, Any] = {}
        
        # Agent names for lazy loading
        self._agent_names = {
            "context_improver": Agent1Output,
            "self_checker": SelfCheckerResult,
            "sensitive_data_detector": SensitiveDataDetectorOutput,
            "pii_sub_agent_worker": PIIWorkerOutput,
        }

    @property
    def model(self):
        """Lazy load the model"""
        if self._model is None:
            try:
                self._model = self.model_loader.init_model_openai_basic()
                logger.info("Model initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize model: {e}")
                raise
        return self._model

    def register_agent(self, name: str, agent: Any) -> None:
        """Register an agent with the given name"""
        self._agents[name] = agent
        logger.debug(f"Agent '{name}' registered successfully")

    def get_agent(self, name: str) -> Optional[Any]:
        """Get an agent by name, creating it if necessary"""
        if name not in self._agents:
            if name in self._agent_names:
                try:
                    self._agents[name] = self.model.with_structured_output(self._agent_names[name])
                    logger.debug(f"Agent '{name}' created and cached")
                except Exception as e:
                    logger.error(f"Failed to create agent '{name}': {e}")
                    return None
            else:
                logger.warning(f"Unknown agent name: {name}")
                return None
        
        return self._agents.get(name)

    # Convenience properties for commonly used agents
    @property
    def context_improver(self):
        """Get the context improver agent"""
        return self.get_agent("context_improver")

    @property
    def self_checker(self):
        """Get the self checker agent"""
        return self.get_agent("self_checker")

    @property
    def sensitive_data_detector(self):
        """Get the sensitive data detector agent"""
        return self.get_agent("sensitive_data_detector")

    @property
    def pii_sub_agent_worker(self):
        """Get the PII sub agent worker"""
        return self.get_agent("pii_sub_agent_worker")

    def list_available_agents(self) -> list:
        """List all available agent names"""
        return list(self._agent_names.keys())

    def clear_cache(self) -> None:
        """Clear the agent cache"""
        self._agents.clear()
        logger.debug("Agent cache cleared")