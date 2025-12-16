from typing import Dict, Any, List
import asyncio
from src.config.logs_config import get_logger
from src.execution.actions.process_qa_auditor_action import ProcessQAAuditorAction
from src.utils.transcript.chunk_original_transcript import chunk_original_transcript

logger = get_logger(__name__)

class ProcessQAAuditorUseCase:
    def __init__(self, action: ProcessQAAuditorAction):
        self.action = action
    
    async def execute(self, process_output: Dict[str, Any]) -> Dict[str, Any]:
        """Process QA auditor for masked transcript validation"""
        logger.info("Starting QA auditor processing")
        
        # Extract required data from process_output

        logger.info(f"Process output keys: {list(process_output.keys())}")

        masked_transcript = process_output.get("masked_transcript", "")
        re_verify_results = process_output.get("re_verify_results", [])
        original_transcript = process_output.get("original_transcript", "")

        if original_transcript:
            logger.info(f"Found original_transcript at top level, length: {len(original_transcript)}")

        if not original_transcript: 
            logger.info(f"Not found original_transcript at top level, length: {len(original_transcript)}")

        # Extract original transcript from the masker_result
        masker_result = process_output.get("masker_result", {})
        logger.info(f"Masker result keys: {list(masker_result.keys()) if masker_result else 'None'}")
        
        # Chunk the original transcript into 100-second chunks
        chunked_result = chunk_original_transcript(original_transcript, chunk_duration=100, overlap_duration=10)
        chunks = chunked_result["chunks"]
        
        logger.info(f"Split transcript into {len(chunks)} chunks for QA processing")
        
        # Process each chunk concurrently
        async def process_chunk_for_qa(chunk_data):
            chunk_id = chunk_data["metadata"]["chunk_index"]
            chunk_start_time = chunk_data.get("metadata", {}).get("start_time", 0)
            chunk_end_time = chunk_data.get("metadata", {}).get("end_time", float('inf'))
            logger.info(f"Processing QA auditor for chunk {chunk_id} (time range: {chunk_start_time}s - {chunk_end_time}s)")
            
            # Filter detections by time range and PASS recommendation for this chunk
            chunk_detections = []
            for result in re_verify_results:
                detection_start = result.get("start_time", 0)
                detection_end = result.get("end_time", 0)
                
                # Check if detection overlaps with chunk time range AND has PASS recommendation
                if detection_end >= chunk_start_time and detection_start <= chunk_end_time:
                    # Only include detections with PASS recommendation for QA Auditor
                    re_verify_result = result.get("re_verify_result", {})
                    recommendation = re_verify_result.get("recommendation", "")
                    
                    if recommendation == "PASS":
                        chunk_detections.append(result)
                        logger.debug(f"Added PASS detection {result.get('detection_id')} at {detection_start}s-{detection_end}s to chunk {chunk_id}")
                    else:
                        logger.debug(f"Skipped {recommendation} detection {result.get('detection_id')} at {detection_start}s-{detection_end}s for chunk {chunk_id}")
            
            logger.info(f"Found {len(chunk_detections)} detections for chunk {chunk_id}")
            
            # Prepare state for QA auditor workflow
            current_chunk_start = chunk_start_time
            
            # Extract only the relevant portion of transcripts for this chunk
            # Keep original timestamps for accurate time matching
            chunk_end_time = chunk_data.get("metadata", {}).get("end_time", 0)
            
            chunk_original_text = self._extract_original_chunk_text(
                chunk_data.get("text", ""),
                chunk_start_time,
                chunk_end_time
            )
            
            chunk_masked_text = self._extract_masked_chunk_text(
                masked_transcript, 
                chunk_start_time,
                chunk_end_time
            )
            
            state = {
                "masked_transcript": chunk_masked_text,
                "original_transcript": chunk_original_text,
                "detections": chunk_detections,
                "chunk_id": chunk_id,
                "current_chunk_start": current_chunk_start,
                "context_direction": "both",
                "context_query": "",
                "qa_auditor_results": {}
            }
            
            try:
                # Execute QA auditor workflow
                result = await self.action.execute(state)
                
                # Store result
                return {
                    "chunk_id": chunk_id,
                    "qa_auditor_result": result,
                    "status": "success"
                }
                
            except Exception as e:
                logger.error(f"QA auditor failed for chunk {chunk_id}: {str(e)}")
                return {
                    "chunk_id": chunk_id,
                    "error": str(e),
                    "status": "failed"
                }
        
        # Process all chunks concurrently
        tasks = [process_chunk_for_qa(chunk) for chunk in chunks]
        qa_results = await asyncio.gather(*tasks)
        
        # Prepare final result
        result = {
            "total_chunks": len(chunks),
            "chunks_with_credit_card": process_output.get("chunks_with_credit_card", 0),
            "qa_auditor_results": qa_results,
            "masked_transcript": masked_transcript,
            "original_transcript": original_transcript,
            "qa_summary": {
                "total_processed": len(qa_results),
                "successful": sum(1 for r in qa_results if r.get("status") == "success"),
                "failed": sum(1 for r in qa_results if r.get("status") == "failed")
            },
            "chunking_config": chunked_result["chunking_config"]
        }
        
        logger.info(f"QA auditor processing completed. Processed {len(qa_results)} chunks.")
        return result

    def _extract_masked_chunk_text(self, masked_transcript: str, start_time: float, end_time: float) -> str:
        """
        Extract only the relevant portion of masked transcript for a chunk.
        Keep original timestamps for accurate time matching.
        
        Args:
            masked_transcript: Full masked transcript with timestamps
            start_time: Start time of the chunk
            end_time: End time of the chunk
            
        Returns:
            Extracted transcript portion with original timestamps
        """
        import re
        
        # Pattern to match transcript lines: [start --> end] [channel]: text
        pattern = r'\[(\d+\.?\d*)\s*-->\s*(\d+\.?\d*)\]\s*\[([^\]]+)\]:\s*(.+)'
        
        lines = masked_transcript.split('\n')
        chunk_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                chunk_lines.append(line)
                continue
                
            match = re.match(pattern, line)
            if match:
                line_start_time = float(match.group(1))
                line_end_time = float(match.group(2))
                channel = match.group(3)
                text = match.group(4)
                
                # Check if this line falls within the chunk time range
                if line_end_time >= start_time and line_start_time <= end_time:
                    # Keep original timestamps for accurate time matching
                    original_line = f"[{line_start_time:.2f} --> {line_end_time:.2f}] [{channel}]: {text}"
                    chunk_lines.append(original_line)
        
        return '\n'.join(chunk_lines)
    
    def _extract_original_chunk_text(self, transcript: str, start_time: float, end_time: float) -> str:
        """
        Extract only the relevant portion of original transcript for a chunk.
        Keep original timestamps for accurate time matching.
        
        Args:
            transcript: Full original transcript with timestamps
            start_time: Start time of the chunk
            end_time: End time of the chunk
            
        Returns:
            Extracted transcript portion with original timestamps
        """
        import re
        
        # Pattern to match transcript lines: [start --> end] [channel]: text
        pattern = r'\[(\d+\.?\d*)\s*-->\s*(\d+\.?\d*)\]\s*\[([^\]]+)\]:\s*(.+)'
        
        lines = transcript.split('\n')
        chunk_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                chunk_lines.append(line)
                continue
                
            match = re.match(pattern, line)
            if match:
                line_start_time = float(match.group(1))
                line_end_time = float(match.group(2))
                channel = match.group(3)
                text = match.group(4)
                
                # Check if this line falls within the chunk time range
                if line_end_time >= start_time and line_start_time <= end_time:
                    # Keep original timestamps for accurate time matching
                    original_line = f"[{line_start_time:.2f} --> {line_end_time:.2f}] [{channel}]: {text}"
                    chunk_lines.append(original_line)
        
        return '\n'.join(chunk_lines)