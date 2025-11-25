from typing import Dict, List, Any
from src.config.logs_config import get_logger
from src.execution.actions.process_transcript_action import ProcessTranscriptAction
from src.execution.actions.process_transcript_reverify_action import ProcessTranscriptReVerifyAction
from src.utils.transcript.chunk_transcript import chunk_transcript
from src.utils.transcript.prase_transcript import parse_transcription
from src.utils.re_verify.timestamp_extraction import extract_detections_with_timestamps
from src.utils.re_verify.context_extraction import prepare_re_verify_input

logger = get_logger(__name__)

class ProcessTranscriptUseCase:
    def __init__(self, action: ProcessTranscriptAction, re_verify_action: ProcessTranscriptReVerifyAction = None):
        self.action = action
        self.re_verify_action = re_verify_action
    
    async def execute(self, transcript_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process transcript for credit card detection"""
        logger.info("Starting transcript processing")
        
        # ถ้าเป็น raw text ให้ parse ก่อน
        if isinstance(transcript_data, str):
            text_length = len(transcript_data)
            line_count = transcript_data.count('\n') + 1
            logger.info(f"UseCase received raw text: {text_length} chars, {line_count} lines")
            
            # Log first and last lines for debugging
            lines = transcript_data.split('\n')
            if lines:
                logger.info(f"UseCase first line: {lines[0][:100]}...")
                logger.info(f"UseCase last line: {lines[-1][:100]}...")
            
            logger.debug("Parsing raw text to JSON structure")
            transcript_data = parse_transcription(transcript_data)
            
            # Log parsing results
            if "segments" in transcript_data:
                segment_count = len(transcript_data["segments"])
                logger.info(f"Parsed {segment_count} segments")
                if segment_count > 0:
                    first_seg = transcript_data["segments"][0]
                    last_seg = transcript_data["segments"][-1]
                    logger.info(f"First segment: [{first_seg['start']} --> {first_seg['end']}] [{first_seg['channel']}]: {first_seg['text'][:50]}...")
                    logger.info(f"Last segment: [{last_seg['start']} --> {last_seg['end']}] [{last_seg['channel']}]: {last_seg['text'][:50]}...")
        
        # Chunk transcript 100 วินาที
        logger.debug("Chunking transcript with 100s windows")
        chunked_result = chunk_transcript(
            json_data=transcript_data,
            chunk_duration=60.0,
            overlap_duration=10.0,
            include_original_text=True
        )
        
        # Process each chunk
        processed_chunks = []
        for chunk in chunked_result["chunks"]:
            logger.debug(f"Processing chunk {chunk['metadata']['chunk_index']}")
            
            # ส่งเข้า workflow
            workflow_result = await self.action.execute(chunk)
            
            # เช็คผลลัพธ์
            has_credit_card = self._has_credit_card_data(workflow_result)
            
            # Always store workflow_result for Payment Agent detection extraction
            subagent_response = workflow_result.get("subagent_response", {})
            
            if has_credit_card:
                # Extract masked credit cards from the new structure
                masking_results = subagent_response.get("masking_results", [])
                
                processed_chunks.append({
                    "chunk_id": chunk["metadata"]["chunk_index"],
                    "has_credit_card": True,
                    "status": "credit_card_found",
                    "masked_credit_cards": masking_results,
                    "summary": subagent_response.get("summary", {}),
                    "timestamp_range": {
                        "start": chunk["metadata"]["chunk_start"],
                        "end": chunk["metadata"]["chunk_end"]
                    },
                    "workflow_result": workflow_result  # Store for Payment Agent detection extraction
                })
            else:
                processed_chunks.append({
                    "chunk_id": chunk["metadata"]["chunk_index"],
                    "has_credit_card": False,
                    "status": "no_credit_card_found",
                    "timestamp_range": {
                        "start": chunk["metadata"]["chunk_start"],
                        "end": chunk["metadata"]["chunk_end"]
                    },
                    "workflow_result": workflow_result  # Store for Payment Agent detection extraction
                })
        
        # สรุมผล
        result = {
            "total_chunks": len(processed_chunks),
            "chunks_with_credit_card": sum(1 for c in processed_chunks if c["has_credit_card"]),
            "processed_chunks": processed_chunks,
            "chunking_info": chunked_result["chunking_config"],
            "processing_summary": {
                "total_duration": chunked_result["chunking_config"]["total_duration"],
                "chunk_size": 60.0,
                "overlap": 10.0
            }
        }
        
        # Re-Verify process (if re_verify_action is provided)
        re_verify_results = []
        if self.re_verify_action and result["chunks_with_credit_card"] > 0:
            logger.info("Starting Re-Verify process for individual detections")
            
            # Extract individual detections with timestamps
            detections = extract_detections_with_timestamps(processed_chunks, before_seconds=30.0, after_seconds=10.0)
            logger.info(f"Found {len(detections)} individual detections for Re-Verify")
            
            # Process each detection individually
            for i, detection in enumerate(detections):
                logger.info(f"Processing detection {i+1}/{len(detections)}: {detection['detection']['type']}")
                
                # Prepare input for re-verify
                re_verify_input = prepare_re_verify_input(detection, transcript_data)
                
                # Execute re-verify workflow
                try:
                    re_verify_result = await self.re_verify_action.execute(re_verify_input)
                    re_verify_results.append({
                        "detection_id": detection["detection"].get("id", f"det_{i}"),
                        "detection_type": detection["detection"]["type"],
                        "original_text": detection["detection"]["original_text"],
                        "re_verify_result": re_verify_result,
                        "context_window": detection["context_window"]
                    })
                    logger.info(f"Re-Verify completed for detection {i+1}")
                except Exception as e:
                    logger.error(f"Re-Verify failed for detection {i+1}: {str(e)}")
                    re_verify_results.append({
                        "detection_id": detection["detection"].get("id", f"det_{i}"),
                        "detection_type": detection["detection"]["type"],
                        "original_text": detection["detection"]["original_text"],
                        "re_verify_result": {"error": str(e)},
                        "context_window": detection["context_window"]
                    })
        
        # Add re-verify results to the main result
        result["re_verify_results"] = re_verify_results
        result["re_verify_summary"] = {
            "total_detections": len(detections) if 'detections' in locals() else 0,
            "processed_detections": len(re_verify_results),
            "successful_re_verifies": sum(1 for r in re_verify_results if "error" not in r.get("re_verify_result", {}))
        }
        
        logger.info(f"Processing complete: {result['chunks_with_credit_card']}/{result['total_chunks']} chunks contain credit cards")
        logger.info(f"Re-Verify complete: {result['re_verify_summary']['successful_re_verifies']}/{result['re_verify_summary']['processed_detections']} detections processed")
        return result
    
    def _has_credit_card_data(self, workflow_result: Dict[str, Any]) -> bool:
        """Check if workflow detected and masked credit cards"""
        # Get subagent_response from workflow result
        subagent_response = workflow_result.get("subagent_response", {})
        
        # Check if we have masking results from the new structure
        masking_results = subagent_response.get("masking_results", [])
        if masking_results:
            # Check if at least one card was successfully masked
            for result in masking_results:
                category = result.get("category", "")
                if category != "No Card" and category in ["Success Mask", "Success Partial"]:
                    return True
        
        # NEW: Check for Payment Agent detections directly
        # Get completed_results to check for Payment Agent detections
        completed_results = workflow_result.get("completed_results", [])
        for result in completed_results:
            if result.get("agent") == "Agent_Payment":
                payment_result = result.get("result", {})
                # Check if Payment Agent detected any PAYMENT type data
                if "detections" in payment_result and payment_result["detections"]:
                    for detection in payment_result["detections"]:
                        if detection.get("pii_type") == "PAYMENT":
                            logger.info(f"Found Payment Agent detection: {detection.get('value', 'N/A')}")
                            return True
                
        return False