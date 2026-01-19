from typing import Any, Dict, Optional

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

from src.agents.schemas.types import (
    AgentPaymentOutput,
    ChooseModelToTranscribeResult,
    ChunkAnalysis,
    CompareChunkWavFilesResult,
    ConsistencyCheckerResult,
    ConsistencyCheckerResultBatch,
    MaskerBatchResult,
    PIIWorkerOutput,
    QAAuditorResult,
    ReVerifyBatchResult,
    ReVerifyResult,
)
from src.agents.tools.tools import (
    get_context_extension,
    get_detections_in_range,
    get_original_text_range,
)
from src.config.logs_config import get_logger
from src.models.langchain_model_loader import LangchainModelLoader

logger = get_logger(__name__)


class AgentManager:
    def __init__(self, model_loader: Optional[LangchainModelLoader] = None):
        self.model_loader = model_loader or LangchainModelLoader()
        self._model = None
        self._agents: Dict[str, Any] = {}

        # Agent names for lazy loading
        self._agent_names = {
            "sensitive_data_detector": ChunkAnalysis,
            "pii_sub_agent_worker": PIIWorkerOutput,
            "agent_payment": AgentPaymentOutput,
            "re_verify_agent": ReVerifyResult,
            "re_verify_batch_agent": ReVerifyBatchResult,
            "consistency_checker": ConsistencyCheckerResult,
            "consistency_checker_batch": ConsistencyCheckerResultBatch,
            "masker_batch_agent": MaskerBatchResult,
            "qa_auditor": QAAuditorResult,
            "compare_chunk_wav_files": CompareChunkWavFilesResult,
            "choose_model_to_transcribe": ChooseModelToTranscribeResult,
        }

        self._agent_tools = {
            "sensitive_data_detector": [],
            "pii_sub_agent_worker": [],
            "agent_payment": [],
            "re_verify_agent": [],
            "re_verify_batch_agent": [],
            "consistency_checker": [],
            "consistency_checker_batch": [],
            "masker_batch_agent": [],
            "qa_auditor": [
                get_context_extension,
                get_detections_in_range,
                get_original_text_range,
            ],
            "compare_chunk_wav_files": [],
            "choose_model_to_transcribe": [],
        }

    @property
    def model(self):
        """Lazy load the model"""
        if self._model is None:
            try:
                self._model = self.model_loader.init_chat_model_inference_server(
                    temperature=0.2
                )
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
                    self._agents[name] = self.model.with_structured_output(
                        self._agent_names[name]
                    )
                    logger.debug(f"Agent '{name}' created and cached")
                except Exception as e:
                    logger.error(f"Failed to create agent '{name}': {e}")
                    return None
            else:
                logger.warning(f"Unknown agent name: {name}")
                return None

        return self._agents.get(name)

    def get_agent_with_tools(self, name: str) -> Optional[Any]:
        """Get an agent by name, creating it if necessary"""
        if name not in self._agents:
            if name in self._agent_names:
                try:
                    self._agents[name] = create_agent(
                        model=self.model,
                        tools=self._agent_tools[name],
                        response_format=ToolStrategy(
                            self._agent_names[name], handle_errors=True
                        ),
                    )
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
    def sensitive_data_detector(self):
        """Get the sensitive data detector agent"""
        return self.get_agent("sensitive_data_detector")

    @property
    def pii_sub_agent_worker(self):
        """Get the PII sub agent worker"""
        return self.get_agent("pii_sub_agent_worker")

    @property
    def agent_payment(self):
        """Get the Agent Payment worker"""
        return self.get_agent("agent_payment")

    @property
    def re_verify(self):
        """Get the Re-Verify agent"""
        return self.get_agent("re_verify_agent")

    @property
    def re_verify_batch(self):
        """Get the Re-Verify batch agent"""
        return self.get_agent("re_verify_batch_agent")

    @property
    def consistency_checker(self):
        """Get the Consistency Checker agent"""
        return self.get_agent("consistency_checker")

    @property
    def consistency_checker_batch(self):
        """Get the Consistency Checker batch agent"""
        return self.get_agent("consistency_checker_batch")

    @property
    def masker_batch(self):
        """Get the Masker batch agent"""
        return self.get_agent("masker_batch_agent")

    @property
    def qa_auditor(self):
        """Get the QA Auditor agent"""
        return self.get_agent("qa_auditor")

    @property
    def compare_chunk_wav_files(self):
        """Get the Compare Chunk Wav Files agent"""
        return self.get_agent("compare_chunk_wav_files")

    @property
    def choose_model_to_transcribe(self):
        """Get the Choose Model to Transcribe agent"""
        return self.get_agent("choose_model_to_transcribe")

    def list_available_agents(self) -> list:
        """List all available agent names"""
        return list(self._agent_names.keys())

    def clear_cache(self) -> None:
        """Clear the agent cache"""
        self._agents.clear()
        logger.debug("Agent cache cleared")
