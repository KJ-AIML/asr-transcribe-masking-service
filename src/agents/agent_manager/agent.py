from langgraph.prebuilt import create_react_agent

from src.models.langchain_model_loader import LangchainModelLoader
from src.agents.prompts.sample_agent_prompt import get_prompt_sample_agent

loader = LangchainModelLoader()

openai_basic_model = loader.init_model_openai_basic()

prompt_sample_agent = get_prompt_sample_agent()

sample_agent = create_react_agent(
    openai_basic_model,
    tools=[],
    prompt=prompt_sample_agent,
)