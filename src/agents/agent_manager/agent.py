from langgraph.prebuilt import create_react_agent

from src.models.langchain_model_loader import LangchainModelLoader
from src.agents.prompts.sample_agent_prompt import get_prompt_sample_agent

loader = LangchainModelLoader()

inference_private_model = loader.init_chat_model_inference_private_server()

prompt_sample_agent = get_prompt_sample_agent()

sample_agent = create_react_agent(
    inference_private_model,
    tools=[],
    prompt=prompt_sample_agent,
)