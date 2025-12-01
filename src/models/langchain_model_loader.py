from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from typing import Optional, Dict, Any
import os

from src.config.settings import settings

class LangchainModelLoader:
    def __init__(self):
        self.models = {}
        self._setup_api_keys()

    def _setup_api_keys(self):
        if settings.OPENAI_API_KEY:
            os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
            os.environ["OPENAI_MODEL_BASIC"] = settings.OPENAI_MODEL_BASIC
            os.environ["OPENAI_MODEL_REASONING"] = settings.OPENAI_MODEL_REASONING
        if settings.INFERENCE_SERVER_API_KEY:
            os.environ["INFERENCE_SERVER_API_KEY"] = settings.INFERENCE_SERVER_API_KEY
            os.environ["INFERENCE_SERVER_MODEL_BASIC"] = settings.INFERENCE_SERVER_MODEL_BASIC
            os.environ["INFERENCE_SERVER_URL"] = settings.INFERENCE_SERVER_URL

    def _get_openai_config(self, **kwargs) -> Dict[str, Any]:
        config = {"temperature": kwargs.get("temperature", 0.0)}
        if "api_key" in kwargs:
            config["api_key"] = kwargs["api_key"]
        elif settings.OPENAI_API_KEY:
            config["api_key"] = settings.OPENAI_API_KEY
        config.update({k: v for k, v in kwargs.items() if k != "temperature"})
        return config

    def init_model_openai_basic(self, temperature: float = 0.0, **kwargs) -> Any:
        config = self._get_openai_config(temperature=temperature, **kwargs)
        model = init_chat_model(model=settings.OPENAI_MODEL_BASIC, **config)
        self.models["openai_basic"] = model
        return model

    def init_model_openai_reasoning(self, temperature: float = 0.0, **kwargs) -> Any:
        config = self._get_openai_config(temperature=temperature, **kwargs)
        model = init_chat_model(model=settings.OPENAI_MODEL_REASONING, **config)
        self.models["openai_reasoning"] = model
        return model

    def init_chat_model_inference_server(self, temperature: float = 0.0, **kwargs) -> Any:
        config = {"temperature": temperature}
        if "api_key" in kwargs:
            config["api_key"] = kwargs["api_key"]
        elif settings.INFERENCE_SERVER_API_KEY:
            config["api_key"] = settings.INFERENCE_SERVER_API_KEY
        config.update({k: v for k, v in kwargs.items() if k != "temperature"})
        
        model = ChatOpenAI(
            model=settings.INFERENCE_SERVER_MODEL_BASIC,
            temperature=temperature,
            top_p=kwargs.get("top_p", 0.90),
            openai_api_key=config["api_key"],
            openai_api_base=settings.INFERENCE_SERVER_URL,
            request_timeout=450,
            max_retries=3,
        )
        self.models["inference_server"] = model
        return model

    def init_chat_model_inference_private_server(self, temperature: float = 0.0, **kwargs) -> Any:
        config = {"temperature": temperature}
        config.update({k: v for k, v in kwargs.items() if k != "temperature"})
        
        model = ChatOllama(
            model=settings.INFERENCE_PRIVATE_SERVER_MODEL_BASIC,
            temperature=temperature,
            top_p=kwargs.get("top_p", 0.90),
            openai_api_base=settings.INFERENCE_PRIVATE_SERVER_URL,
        )
        self.models["inference_private_server"] = model
        return model

    def get_model(self, model_name: str) -> Optional[Any]:
        return self.models.get(model_name)

    def list_available_models(self) -> list:
        return list(self.models.keys())
