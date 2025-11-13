from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Send

from src.agents.schemas.types import (
    State,
    WorkerState,
    SynthesizedPIIResult,
)
from src.agents.agent_manager.agent_manager import AgentManager
from src.agents.prompts.prompt_manager import PromptManager
from src.config.logs_config import get_logger

# Initialize managers
agent_manager = AgentManager()
prompt_manager = PromptManager()

logger = get_logger(__name__)

# Nodes
def llm_call_context_improver(state: State):
    # Convert transcript to string if it's a dict

    logger.info("=== Processing transcript with context improver node ===")
    
    if state.get("self_checker_feedback_status") == "FAIL":

        logger.info("=== Feedback found, processing transcript with context improver node ===")

        messages = [
            SystemMessage(content=prompt_manager.context_improver),
            HumanMessage(content=f"""
            Rewrite the transcript based on feedback:

            ### Feedback:
            {state['feedback']}

            ### Issues Found:
            {state['issue_found']}

            ### Improved Transcript:
            {str(state['improved_transcript'])}
            """)
        ]
    else:

        logger.info("=== No feedback found, passing original transcript ===")

        messages = [
            SystemMessage(content=prompt_manager.context_improver),
            HumanMessage(content=str(state['original_transcript']))
        ]
    
    response = agent_manager.context_improver.invoke(messages)

    logger.info("=== Context Improver Node Success ===")

    return {"improved_transcript": response.model_dump()}

def llm_call_self_checker(state: State):

    logger.info("=== Processing transcript with self checker node ===")
    
    messages = [
        SystemMessage(content=prompt_manager.self_checker),
        HumanMessage(content=str(state['improved_transcript']))
    ]
    
    response = agent_manager.self_checker.invoke(messages)

    logger.info("=== Self Checker Node Success ===")
    logger.info(f"=== Self Checker Status: {response.status} ===")
    logger.info(f"=== Feedback for Agent 1: {response.feedback_for_agent_1} ===")
    return {
        "self_checker_feedback_status": response.status,
        "feedback": response.feedback_for_agent_1.model_dump() if response.feedback_for_agent_1 else None,
        "issue_found": [issue.model_dump() for issue in response.issues_found] if response.issues_found else None
    }

def llm_call_sensitive_data_classify(state: State):

    logger.info("=== Processing transcript with sensitive data classify node ===")
        
    messages = [
        SystemMessage(content=prompt_manager.pii_router),
        HumanMessage(content=str(state['improved_transcript']))
    ]
    
    response = agent_manager.sensitive_data_detector.invoke(messages)

    logger.info("=== Sensitive Data Classify Node Success ===")
    return {"sensitive_data_detected": response.model_dump()}

def assign_pii_workers(state: State):
    """Assign PII workers based on sensitive data classification"""
    
    logger.info("=== Assigning PII Workers ===")
    # อ่านจาก sensitive_data_classify
    results = state['sensitive_data_detected']['results']
    
    sends = []
    for chunk_result in results:
        routing_plan = chunk_result['routing_plan']
        parallel_agents = routing_plan['parallel_agents']
        pii_categories = chunk_result['pii_categories_detected']

        logger.info(f"Parallel agents: {parallel_agents}")
        
        for agent_name in parallel_agents:
            relevant_pii = [
                pii for pii in pii_categories 
                if pii['required_agent'] == agent_name
            ]
            
            sends.append(
                Send("pii_worker", {
                    "agent_name": agent_name,
                    "pii_info": relevant_pii,
                    "transcript": state['improved_transcript']
                })
            )
    
    logger.info(f"Total workers assigned: {len(sends)}")
    return sends

def pii_worker(state: WorkerState):
    """Process PII data for a specific agent"""
    
    logger.info(f"=== PII Worker Started: {state['agent_name']} ===")
    logger.info(f"PII Categories: {[p['category'] for p in state['pii_info']]}")

    # Map AgentName กับ subagents config
    agent_map = {
        "Agent_Name": "agent_name",
        "Agent_ID_Card": "agent_id_card",
        "Agent_DOB": "agent_dob",
        "Agent_Phone": "agent_phone",
        "Agent_Address": "agent_address",
        "Agent_Email": "agent_email",
        "Agent_Coverage": "agent_coverage",
        "Agent_Premium": "agent_premium",
        "Agent_Payment": "agent_payment",
        "Agent_License": "agent_license",
        "Agent_Health": "agent_health",
        "Agent_Beneficiary": "agent_beneficiary",
        "Agent_Other": "agent_other",
    }
    
    agent_config_name = agent_map.get(state['agent_name'])
    agent_config = prompt_manager.subagents.get(agent_config_name)
    
    if not agent_config:
        return {"completed_results": [{"error": f"Agent {state['agent_name']} not found"}]}
    
    messages = [
        SystemMessage(content=agent_config['system_prompt']),
        HumanMessage(content=f"""
        Agent: {state['agent_name']}
        PII Information: {state['pii_info']}
        Transcript: {state['transcript']}
        """)
    ]
    
    result = agent_manager.pii_sub_agent_worker.invoke(messages)
    
    logger.info(f"=== PII Worker Completed: {state['agent_name']} ===")
    return {"completed_results": [{
        "agent": state['agent_name'],
        "pii_processed": state['pii_info'],
        "result": result.model_dump()
    }]}

def synthesizer(state: State):
    """Synthesize results from all workers"""
    logger.info("=== Synthesizer Started ===")
    logger.info(f"Total results to synthesize: {len(state['completed_results'])}")
    
    # Collect all detections from workers
    all_detections = []
    worker_results = []
    
    for result in state['completed_results']:
        if 'error' in result:
            logger.error(f"Error in worker: {result['error']}")
            continue
            
        worker_results.append(result['result'])
        
        # Extract detections if available
        if 'detections' in result['result']:
            all_detections.extend(result['result']['detections'])
    
    # Count censoring segments
    total_censor = sum(1 for d in all_detections if d.get('should_censor', False))
    
    # Determine overall status
    has_errors = any('error' in r for r in state['completed_results'])
    if has_errors:
        overall_status = "partial"
    elif len(worker_results) == 0:
        overall_status = "failed"
    else:
        overall_status = "complete"
    
    logger.info(f"=== Synthesizer Completed: {overall_status} ===")
    
    return {
        "subagent_response": SynthesizedPIIResult(
            chunk_id="combined",
            all_detections=all_detections,
            worker_results=worker_results,
            total_pii_found=len(all_detections),
            total_censor_segments=total_censor,
            conflicts=[],
            overall_status=overall_status
        ).model_dump()
    }

def route_check(state: State):
    """Route back to need improve or end based upon feedback from the self checker"""

    if state["self_checker_feedback_status"] == "PASS":
        logger.info("Self Checker Node Pass")
        return "Accepted"
    elif state["self_checker_feedback_status"] == "FAIL":
        logger.info("Self Checker Node Fail")
        return "Rejected"
