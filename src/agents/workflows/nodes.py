import json
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Send

from src.agents.schemas.types import (
    State,
    WorkerState,
    SynthesizedPIIResult,

    ReVerifyState
)
from src.agents.agent_manager.agent_manager import AgentManager
from src.agents.prompts.prompt_manager import PromptManager
from src.config.logs_config import get_logger
from src.utils.transcript.calculate_time_stamp import calculate_word_timing

# Initialize managers
agent_manager = AgentManager()
prompt_manager = PromptManager()

logger = get_logger(__name__)

# Nodes
async def llm_call_context_improver(state: State):
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
    
    response = await agent_manager.context_improver.ainvoke(messages)

    logger.info("=== Context Improver Node Success ===")

    return {"improved_transcript": response.model_dump()}

async def llm_call_self_checker(state: State):

    logger.info("=== Processing transcript with self checker node ===")
    
    messages = [
        SystemMessage(content=prompt_manager.self_checker),
        HumanMessage(content=str(state['improved_transcript']))
    ]
    
    response = await agent_manager.self_checker.ainvoke(messages)

    logger.info("=== Self Checker Node Success ===")
    logger.info(f"=== Self Checker Status: {response.status} ===")
    logger.info(f"=== Feedback for Agent 1: {response.feedback_for_agent_1} ===")
    return {
        "self_checker_feedback_status": response.status,
        "feedback": response.feedback_for_agent_1.model_dump() if response.feedback_for_agent_1 else None,
        "issue_found": [issue.model_dump() for issue in response.issues_found] if response.issues_found else None
    }

async def llm_call_sensitive_data_classify(state: State):

    logger.info("=== Processing transcript with sensitive data classify node ===")
        
    messages = [
        SystemMessage(content=prompt_manager.pii_router),
        HumanMessage(content=str(state['text_and_segment']))
    ]
    
    response = await agent_manager.sensitive_data_detector.ainvoke(messages)

    logger.info("=== Sensitive Data Classify Node Success ===")
    # Return as a list with a single item to match expected format
    return {"sensitive_data_detected": [response.model_dump()]}

async def assign_pii_workers(state: State):
    """Assign PII workers based on sensitive data classification"""
    
    logger.info("=== Assigning PII Workers ===")
    # อ่านจาก sensitive_data_classify
    results = state['sensitive_data_detected']
    
    sends = []
    for chunk_result in results:
        routing_plan = chunk_result['routing_plan']
        route_to_payment_agent = routing_plan['route_to_payment_agent']
        credit_card_sections = chunk_result['credit_card_sections']

        logger.info(f"Route to payment agent: {route_to_payment_agent}")
        logger.info(f"Credit card sections: {credit_card_sections}")
        
        if not route_to_payment_agent:
            continue

        card_number_data = []
        expiration_date_data = []
        cvv_data = []
        cardholder_name_data = []
        
        # CRITICAL: Validate that we have actual credit card data with digits
        has_valid_credit_card_data = False
        
        for section in credit_card_sections:
            section_type = section['section_type']
            
            # Check if this section has actual digits
            total_digits = section.get('total_digits_detected', 0)
            digit_groups = section.get('digit_groups', [])
            
            # CRITICAL FIX: If digit_groups is None but total_digits > 0, still process
            # This handles cases where PII Router detected digits but didn't populate digit_groups
            if total_digits and total_digits > 0:
                has_valid_credit_card_data = True
                logger.info(f"Section {section_type} has {total_digits} digits - processing")
            elif digit_groups and len(digit_groups) > 0:
                has_valid_credit_card_data = True
                logger.info(f"Section {section_type} has {len(digit_groups)} digit groups - processing")
            else:
                logger.warning(f"Skipping section {section_type} - no digits detected (total_digits: {total_digits}, digit_groups: {digit_groups})")
                continue
                
            # For ID cards (typically 13 digits), skip if it's clearly an ID card
            if total_digits == 13:
                evidence_text = ' '.join(section.get('evidence', []))
                if 'บัตรประชาชน' in evidence_text or 'id card' in evidence_text.lower():
                    logger.warning(f"Skipping ID card section with {total_digits} digits")
                    has_valid_credit_card_data = False  # Reset if this was the only section
                    continue
            
            # Mark that we have valid credit card data
            has_valid_credit_card_data = True
            
            section_data = {
                "confidence": section['confidence'],
                "evidence": section['evidence'],
                "segment_ids": section['segment_ids'],
                "timestamp_range": section['timestamp_range'],
                "total_digits_detected": section.get('total_digits_detected'),
                "digit_groups": section.get('digit_groups', []),
                "acknowledgment_segments": section.get('acknowledgment_segments', [])
            }
            
            if section_type in ["SEQUENTIAL_SPELLING", "FULL_MENTION", "AGENT_CONFIRMATION", "credit_card_number_request", "Credit Card Number", "credit_card_number", "Credit Card Number Segment"]:
                card_number_data.append(section_data)
            elif section_type == "EXPIRY_DATE":
                expiration_date_data.append(section_data)
            elif section_type == "CVV":
                cvv_data.append(section_data)
            # Note: cardholder_name is not a standard section_type in the schema
        
        logger.info(f"Card number data: {card_number_data}")
        logger.info(f"Expiration date data: {expiration_date_data}")
        logger.info(f"CVV data: {cvv_data}")
        logger.info(f"Has valid credit card data: {has_valid_credit_card_data}")
        
        # CRITICAL: Only send to Payment Agent if we have valid credit card data with digits
        if route_to_payment_agent and has_valid_credit_card_data and (card_number_data or expiration_date_data or cvv_data):
            all_segment_ids = set()
            for section in credit_card_sections:
                all_segment_ids.update(section['segment_ids'])
                if 'acknowledgment_segments' in section and section['acknowledgment_segments'] is not None:
                    all_segment_ids.update(section['acknowledgment_segments'])
            
            relevant_segments = []
            segments_data = state.get('segments', state.get('text_and_segment', {}).get('segments', []))
            for segment in segments_data:
                if segment.get('id') in all_segment_ids:
                    relevant_segments.append(segment)
            
            payment_data = {
                "chunk_id": chunk_result['chunk_id'],
                "card_number_sections": card_number_data,
                "expiration_date_sections": expiration_date_data,
                "cvv_sections": cvv_data,
                "cardholder_name_sections": cardholder_name_data,
                "routing_confidence": routing_plan.get('confidence', 0.0),
                "transcript": state.get('original_transcript', state.get('transcript', {})),
                "relevant_segments": relevant_segments, 
                "all_segment_ids": list(all_segment_ids) 
            }
            
            # Only send to worker if we have valid payment data
            if payment_data and (card_number_data or expiration_date_data or cvv_data or cardholder_name_data):
                # Convert payment_data to expected format with category
                pii_info_data = {
                    "category": "credit_card",
                    "chunk_id": payment_data["chunk_id"],
                    "card_number_sections": payment_data["card_number_sections"],
                    "expiration_date_sections": payment_data["expiration_date_sections"],
                    "cvv_sections": payment_data["cvv_sections"],
                    "cardholder_name_sections": payment_data["cardholder_name_sections"],
                    "routing_confidence": payment_data["routing_confidence"],
                    "relevant_segments": payment_data["relevant_segments"],
                    "all_segment_ids": payment_data["all_segment_ids"]
                }
                
                # Debug: Log data being sent to Payment Agent
                logger.info(f"DEBUG: Sending to Payment Agent - card_number_sections: {len(pii_info_data['card_number_sections'])}")
                logger.info(f"DEBUG: Card number data: {pii_info_data['card_number_sections']}")
                
                sends.append(
                    Send("pii_worker", {
                        "agent_name": "Agent_Payment",
                        "pii_info": [pii_info_data],
                        "transcript": state.get('original_transcript', state.get('transcript', {})),
                        "text_and_segment": state.get('text_and_segment', {})
                    })
                )

        # for agent_name in route_to_payment_agent:
        #     relevant_pii = [
        #         pii for pii in pii_categories 
        #         if pii['required_agent'] == agent_name
        #     ]
            
            # sends.append(
            #     Send("pii_worker", {
            #         "agent_name": agent_name,
            #         "pii_info": relevant_pii,
            #         "transcript": state['original_transcript']
            #     })
            # )
    
    logger.info(f"Total workers assigned: {len(sends)}")
    return sends

async def pii_worker(state: WorkerState):
    """Process PII data for a specific agent"""
    
    logger.info(f"=== PII Worker Started: {state['agent_name']} ===")
    logger.info(f"PII Categories: {[p['category'] for p in state['pii_info']]}")

    # Map AgentName กับ subagents config
    agent_map = {
        "Agent_Payment": "agent_payment",
    }
    
    agent_config_name = agent_map.get(state['agent_name'])
    agent_config = prompt_manager.subagents.get(agent_config_name)
    
    if not agent_config:
        return {"completed_results": [{"error": f"Agent {state['agent_name']} not found"}]}
    
    overview_text = ""
    if 'text_and_segment' in state:
        overview_text = state['text_and_segment'].get('text', '')
    
    # Debug: Log PII info content before sending to Payment Agent
    # logger.info(f"DEBUG: PII Info content for {state['agent_name']}: {state['pii_info']}")
    
    messages = [
        SystemMessage(content=agent_config['system_prompt']),
        HumanMessage(content=f"""
        Agent: 
        {state['agent_name']}

        PII Information: 
        {state['pii_info']}

        Overview Text: 
        {overview_text}
        """)
    ]

    # logger.info(f"Messages Before ainvoke Agent Payment: Agent: {state['agent_name']},\n PII Information: {state['pii_info']},\n Overview Text: {overview_text}")
    
    result = await agent_manager.pii_sub_agent_worker.ainvoke(messages)
    
    logger.info(f"DEBUG: Payment Agent result: {result}")

    logger.info(f"=== PII Worker Completed: {state['agent_name']} ===")
    return {"completed_results": [{
        "agent": state['agent_name'],
        "pii_processed": state['pii_info'],
        "result": result.model_dump()
    }]}

async def synthesizer(state: State):
    """Synthesize results from all workers"""
    logger.info("=== Synthesizer Started ===")
    logger.info(f"Total results to synthesize: {len(state['completed_results'])}")
    
    # Collect all masking results from workers
    masking_results = []
    worker_results = []
    
    for result in state['completed_results']:
        if 'error' in result:
            logger.error(f"Error in worker: {result['error']}")
            continue
            
        worker_results.append(result['result'])
        
        # Extract masking results from Agent_Payment format
        if 'masking_results' in result['result'] and result['result']['masking_results']:
            masking_data = result['result']['masking_results']
            if 'masking_results' in masking_data:
                # Filter out "No Card" entries to avoid duplicates
                valid_masking_results = [
                    mr for mr in masking_data['masking_results']
                    if mr.get("category") != "No Card"
                ]
                
                # Calculate word-level timing for each masking result
                for masking_result in valid_masking_results:
                    timing = calculate_word_timing(masking_result, state.get('segments', []))
                    
                    # Create result following MaskingResult schema directly
                    result_item = {
                        "type": masking_result.get("type"),
                        "original_text": masking_result.get("original_text"),
                        "masked_text": masking_result.get("masked_text"),
                        "start_time": timing["start_time"],
                        "end_time": timing["end_time"],
                        "segment_ids": masking_result.get("segment_ids"),
                        "confidence": masking_result.get("confidence"),
                        "category": masking_result.get("category")
                    }
                    masking_results.append(result_item)
    
    # Create summary statistics
    summary = {
        "total_masked": len(masking_results),
        "success_mask": sum(1 for mr in masking_results if mr["category"] == "Success Mask"),
        "success_partial": sum(1 for mr in masking_results if mr["category"] == "Success Partial"),
        "overmask_issues": sum(1 for mr in masking_results if mr["category"] in ["Success Overmask", "Fail Overmask"]),
        "missing_mask": sum(1 for mr in masking_results if mr["category"] == "Missing Mask"),
        "wrong_mask": sum(1 for mr in masking_results if mr["category"] == "Wrong Mask")
    }
    
    # Determine overall status
    has_errors = any('error' in r for r in state['completed_results'])
    if has_errors:
        overall_status = "partial"
    elif len(worker_results) == 0:
        overall_status = "failed"
    else:
        overall_status = "complete"
    
    logger.info(f"=== Synthesizer Completed: {overall_status} ===")
    
    # Return output following AgentPaymentOutput schema
    return {
        "subagent_response": {
            "chunk_id": "combined",
            "masking_results": masking_results,
            "summary": summary,
            "overall_status": overall_status
        }
    }

async def route_check(state: State):
    """Route back to need improve or end based upon feedback from the self checker"""

    if state["self_checker_feedback_status"] == "PASS":
        logger.info("Self Checker Node Pass")
        return "Accepted"
    elif state["self_checker_feedback_status"] == "FAIL":
        logger.info("Self Checker Node Fail")
        return "Rejected"

async def llm_call_re_verify(state: ReVerifyState):         
    """Call LLM to re-verify detections"""
    logger.info("=== Processing transcript with re-verify node ===")
    
    # Extract detection data from state
    detection_data = state.get('detection_data', {})
    context_text = detection_data.get('context_text', '')
    detection = detection_data.get('detection', {})
    segments = detection_data.get('segments', [])
    context_window = detection_data.get('context_window', {})
        
    # logger.info(f"Formatted Input: {formatted_input}")

    messages = [
        SystemMessage(content=prompt_manager.re_verify),
        HumanMessage(content=f"""
        Please re-verify the following detection:
        
        ###Detection: {detection}

        ###Context Text: {context_text}

        ###Segments: {segments}

        ###Context Window: {context_window}
        """)
    ]
    
    response = await agent_manager.re_verify.ainvoke(messages)

    logger.info("=== Re-Verify Node Success ===")

    logger.info(f"Re-Verify Response: {response.model_dump()}")

    improve_messages = [
        SystemMessage(content=prompt_manager.consistency_checker),
        HumanMessage(content=response.model_dump_json())
    ]
    
    improve_response = await agent_manager.consistency_checker.ainvoke(improve_messages)
    
    logger.info(f"Consistency Checker Response: {improve_response.model_dump()}")
    
    return {"re_verify_results": [improve_response.model_dump()]}

async def llm_call_missing_detection(state: ReVerifyState):
    """Call LLM to verify missing detections"""
    logger.info("=== Processing transcript with missing detection node ===")
        
    messages = [
        SystemMessage(content=prompt_manager.missing_detection),
        HumanMessage(content=str(state['text_and_segment']))
    ]
    
    response = await agent_manager.missing_detection.ainvoke(messages)

    logger.info("=== Missing Detection Node Success ===")
    # Return as a list with a single item to match expected format
    return {"missing_detection_results": [response.model_dump()]}
