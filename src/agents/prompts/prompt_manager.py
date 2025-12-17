from typing import Dict, Any, Optional
from pathlib import Path
from src.utils.file.markdown_utils import read_markdown_file_with_dedent
from src.config.logs_config import get_logger

logger = get_logger(__name__)

class PromptManager:
    def __init__(self, prompt_base_path: Optional[str] = None):
        # Base path for prompt files
        self.prompt_base_path = Path(prompt_base_path) if prompt_base_path else Path("src/agents/prompts")
        
        # Cache for loaded prompts
        self._subagents: Optional[Dict[str, Any]] = None
        self._context_improver: Optional[str] = None
        self._self_checker: Optional[str] = None
        self._pii_router: Optional[str] = None
        self._re_verify: Optional[str] = None
        self._re_verify_batch: Optional[str] = None
        self._consistency_checker: Optional[str] = None
        self._consistency_checker_batch: Optional[str] = None
        self._masker_batch: Optional[str] = None
        self._qa_auditor: Optional[str] = None
        self._compare_chunk_wav_files: Optional[str] = None
        self._choose_model_to_transcribe: Optional[str] = None
        
        # Subagent configurations
        self._subagent_configs = [
            # {"name": "agent_name", "description": "ทำงานด้าน Name", "file": "agents/agent_name.md"},
            # {"name": "agent_id_card", "description": "ทำงานด้าน ID Card", "file": "agents/agent_id_card.md"},
            # {"name": "agent_dob", "description": "ทำงานด้าน DOB", "file": "agents/agent_dob.md"},
            # {"name": "agent_phone", "description": "ทำงานด้าน Phone", "file": "agents/agent_phone.md"},
            # {"name": "agent_address", "description": "ทำงานด้าน Address", "file": "agents/agent_address.md"},
            # {"name": "agent_email", "description": "ทำงานด้าน Email", "file": "agents/agent_email.md"},
            # {"name": "agent_coverage", "description": "ทำงานด้าน Coverage", "file": "agents/agent_coverage.md"},
            # {"name": "agent_premium", "description": "ทำงานด้าน Premium", "file": "agents/agent_premium.md"},
            {"name": "agent_payment", "description": "ทำงานด้าน Payment", "file": "agents/agent_payment.md"},
            # {"name": "agent_license", "description": "ทำงานด้าน License", "file": "agents/agent_license.md"},
            # {"name": "agent_health", "description": "ทำงานด้าน Health", "file": "agents/agent_health.md"},
            # {"name": "agent_beneficiary", "description": "ทำงานด้าน Beneficiary", "file": "agents/agent_beneficiary.md"},
            # {"name": "agent_other", "description": "ทำงานด้าน Other", "file": "agents/agent_other.md"}
        ]
    
    @property
    def subagents(self) -> Dict[str, Any]:
        """Lazy load all subagent configurations"""
        if self._subagents is None:
            self._subagents = self._load_subagents()
            logger.info(f"Loaded {len(self._subagents)} subagent configurations")
        return self._subagents
    
    @property
    def context_improver(self) -> str:
        """Lazy load context improver prompt"""
        if self._context_improver is None:
            self._context_improver = self._load_prompt("agents/context_improver.md")
            logger.debug("Context improver prompt loaded")
        return self._context_improver
    
    @property
    def self_checker(self) -> str:
        """Lazy load self checker prompt"""
        if self._self_checker is None:
            self._self_checker = self._load_prompt("agents/self_checker.md")
            logger.debug("Self checker prompt loaded")
        return self._self_checker

    @property
    def pii_router(self) -> str:
        """Lazy load PII router prompt"""
        if self._pii_router is None:
            self._pii_router = self._load_prompt("agents/agent_pii_router.md")
            logger.debug("PII router prompt loaded")
        return self._pii_router
        
    @property
    def re_verify(self) -> str:
        """Lazy load Re-Verify prompt"""
        if self._re_verify is None:
            self._re_verify = self._load_prompt("agents/agent_re_verify.md")
            logger.debug("Re-Verify prompt loaded")
        return self._re_verify

    @property
    def re_verify_batch(self) -> str:
        """Lazy load Re-Verify batch prompt"""
        if self._re_verify_batch is None:
            self._re_verify_batch = self._load_prompt("agents/agent_re_verify_batch.md")
            logger.debug("Re-Verify batch prompt loaded")
        return self._re_verify_batch

    @property
    def consistency_checker(self) -> str:
        """Lazy load Consistency Checker prompt"""
        if self._consistency_checker is None:
            self._consistency_checker = self._load_prompt("agents/agent_consistency_checker.md")
            logger.debug("Consistency Checker prompt loaded")
        return self._consistency_checker

    @property
    def consistency_checker_batch(self) -> str:
        """Lazy load Consistency Checker batch prompt"""
        if self._consistency_checker_batch is None:
            self._consistency_checker_batch = self._load_prompt("agents/agent_consistency_checker_batch.md")
            logger.debug("Consistency Checker batch prompt loaded")
        return self._consistency_checker_batch

    @property
    def masker_batch(self) -> str:
        """Lazy load Masker batch prompt"""
        if self._masker_batch is None:
            self._masker_batch = self._load_prompt("agents/agent_masker_batch.md")
            logger.debug("Masker batch prompt loaded")
        return self._masker_batch

    @property
    def qa_auditor(self) -> str:
        """Lazy load QA Auditor prompt"""
        if self._qa_auditor is None:
            self._qa_auditor = self._load_prompt("agents/agent_qa_auditor.md")
            logger.debug("QA Auditor prompt loaded")
        return self._qa_auditor
    
    @property
    def missing_detection(self) -> str:
        """Lazy load Missing Detection prompt"""
        if self._missing_detection is None:
            self._missing_detection = self._load_prompt("agents/agent_missing_detection.md")
            logger.debug("Missing Detection prompt loaded")
        return self._missing_detection

    @property
    def compare_chunk_wav_files(self) -> str:
        """Lazy load Compare Chunk Wav Files prompt"""
        if self._compare_chunk_wav_files is None:
            self._compare_chunk_wav_files = self._load_prompt("agents/agent_compare_chunk_wav_files.md")
            logger.debug("Compare Chunk Wav Files prompt loaded")
        return self._compare_chunk_wav_files
    
    @property
    def choose_model_to_transcribe(self) -> str:
        """Lazy load Choose Model to Transcribe prompt"""
        if self._choose_model_to_transcribe is None:
            self._choose_model_to_transcribe = self._load_prompt("agents/agent_choose_model_to_transcribe.md")
            logger.debug("Choose Model to Transcribe prompt loaded")
        return self._choose_model_to_transcribe


    def _load_subagents(self) -> Dict[str, Any]:
        """Load all subagent configurations"""
        subagents = []
        
        for config in self._subagent_configs:
            try:
                prompt_path = self.prompt_base_path / config["file"]
                system_prompt = read_markdown_file_with_dedent(str(prompt_path))
                
                subagents.append({
                    "name": config["name"],
                    "description": config["description"],
                    "system_prompt": system_prompt,
                })
                
                logger.debug(f"Loaded subagent '{config['name']}' from {config['file']}")
                
            except Exception as e:
                logger.error(f"Failed to load subagent '{config['name']}' from {config['file']}: {e}")
                # Add error placeholder
                subagents.append({
                    "name": config["name"],
                    "description": config["description"],
                    "system_prompt": f"Error: Could not load prompt file for {config['name']}",
                })
        
        return {agent["name"]: agent for agent in subagents}
    
    def _load_prompt(self, filename: str) -> str:
        """Load a single prompt file"""
        try:
            prompt_path = self.prompt_base_path / filename
            return read_markdown_file_with_dedent(str(prompt_path))
        except Exception as e:
            logger.error(f"Failed to load prompt '{filename}': {e}")
            return f"Error: Could not load prompt file '{filename}'"
    
    def get_subagent(self, name: str) -> Optional[Dict[str, Any]]:
        """Get specific subagent configuration"""
        return self.subagents.get(name)
    
    def get_all_subagents(self) -> Dict[str, Any]:
        """Get all subagent configurations"""
        return self.subagents
    
    def reload_prompt(self, prompt_type: str) -> bool:
        """Reload a specific prompt"""
        if prompt_type == "context_improver":
            self._context_improver = None
            return True
        elif prompt_type == "self_checker":
            self._self_checker = None
            return True
        elif prompt_type == "pii_router":
            self._pii_router = None
            return True
        elif prompt_type == "subagents":
            self._subagents = None
            return True
        else:
            logger.warning(f"Unknown prompt type: {prompt_type}")
            return False
    
    def reload_all_prompts(self) -> None:
        """Reload all prompts"""
        self._subagents = None
        self._context_improver = None
        self._self_checker = None
        self._pii_router = None
        logger.info("All prompts cache cleared")
    
    def list_available_subagents(self) -> list:
        """List all available subagent names"""
        return [config["name"] for config in self._subagent_configs]