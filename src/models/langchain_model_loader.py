from langchain.chat_models import init_chat_model
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

    def _get_openai_config(self, **kwargs) -> Dict[str, Any]:
        config = {"temperature": kwargs.get("temperature", 0.0)}
        if "api_key" in kwargs:
            config["api_key"] = kwargs["api_key"]
        elif settings.OPENAI_API_KEY:
            config["api_key"] = settings.OPENAI_API_KEY
        config.update({k: v for k, v in kwargs.items() if k != "temperature"})
        return config

    def _get_google_config(self, **kwargs) -> Dict[str, Any]:
        config = {"temperature": kwargs.get("temperature", 0.0)}
        if "api_key" in kwargs:
            config["api_key"] = kwargs["api_key"]
        elif settings.GOOGLE_API_KEY:
            config["api_key"] = settings.GOOGLE_API_KEY
        config.update({k: v for k, v in kwargs.items() if k != "temperature"})
        return config

    def init_model_openai_basic(self, temperature: float = 0.0, **kwargs) -> Any:
        config = self._get_openai_config(temperature=temperature, **kwargs)
        model = init_chat_model(model="openai:gpt-5-mini", **config)
        self.models["openai_basic"] = model
        return model

    def init_model_openai_reasoning(self, temperature: float = 0.0, **kwargs) -> Any:
        config = self._get_openai_config(temperature=temperature, **kwargs)
        model = init_chat_model(model="openai:gpt-5", **config)
        self.models["openai_reasoning"] = model
        return model

    def init_model_google_basic(self, temperature: float = 0.0, **kwargs) -> Any:
        config = self._get_google_config(temperature=temperature, **kwargs)
        model = init_chat_model(model="google_genai:gemini-flash-latest", **config)
        self.models["google_basic"] = model
        return model

    def init_model_google_reasoning(self, temperature: float = 0.0, **kwargs) -> Any:
        config = self._get_google_config(temperature=temperature, **kwargs)
        model = init_chat_model(model="google_genai:gemini-flash-latest", **config)
        self.models["google_reasoning"] = model
        return model

    def get_model(self, model_name: str) -> Optional[Any]:
        return self.models.get(model_name)

    def list_available_models(self) -> list:
        return list(self.models.keys())
