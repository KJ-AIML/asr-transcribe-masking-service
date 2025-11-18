from typing import Dict, List, Any
from src.config.logs_config import get_logger
from src.execution.actions.process_transcript_action import ProcessTranscriptAction
from src.utils.transcript.chunk_transcript import chunk_transcript
from src.utils.transcript.prase_transcript import parse_transcription

logger = get_logger(__name__)

class ProcessTranscriptUseCase:
    def __init__(self, action: ProcessTranscriptAction):
        self.action = action
    
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
            
            if has_credit_card:
                # Extract masked credit cards from the new structure
                subagent_response = workflow_result.get("subagent_response", {})
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
                    }
                })
            else:
                processed_chunks.append({
                    "chunk_id": chunk["metadata"]["chunk_index"],
                    "has_credit_card": False,
                    "status": "no_credit_card_found",
                    "timestamp_range": {
                        "start": chunk["metadata"]["chunk_start"],
                        "end": chunk["metadata"]["chunk_end"]
                    }
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
        
        logger.info(f"Processing complete: {result['chunks_with_credit_card']}/{result['total_chunks']} chunks contain credit cards")
        return result
    
    def _has_credit_card_data(self, workflow_result: Dict[str, Any]) -> bool:
        """Check if workflow detected and masked credit cards"""
        # Get subagent_response from workflow result
        subagent_response = workflow_result.get("subagent_response", {})
        
        # Check if we have masking results from the new structure
        masking_results = subagent_response.get("masking_results", [])
        if not masking_results:
            return False
            
        # Check if at least one card was successfully masked
        for result in masking_results:
            category = result.get("category", "")
            if category != "No Card" and category in ["Success Mask", "Success Partial"]:
                return True
                
        return False