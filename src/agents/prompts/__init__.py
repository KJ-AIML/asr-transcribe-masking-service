from .prompt_manager import PromptManager

# Create a single instance
prompt_manager = PromptManager()


# Export convenience functions
def get_subagent(name: str):
    return prompt_manager.get_subagent(name)


def get_all_subagents():
    return prompt_manager.get_all_subagents()


def get_context_improver_prompt():
    return prompt_manager.context_improver


def get_self_checker_prompt():
    return prompt_manager.self_checker


def get_pii_router_prompt():
    return prompt_manager.pii_router
