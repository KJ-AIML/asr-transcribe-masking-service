from typing import Dict, Any, List
import asyncio
from src.config.logs_config import get_logger
from src.agents.workflows.build import build_masker_workflow
from src.utils.transcript.chunk_transcript import chunk_transcript
from src.utils.transcript.prase_transcript import parse_transcription

logger = get_logger(__name__)

class ProcessTranscriptMaskerAction:
    def __init__(self):
        self._workflow = None
    
    async def execute(self, masker_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process masker data through masker workflow"""
        logger.info("Starting masker processing for masker data")
        
        try:
            # Build workflow if needed
            if self._workflow is None:
                logger.debug("Building masker workflow for first time")
                self._workflow = build_masker_workflow()
            
            # Extract data from masker_data
            transcript = masker_data.get("transcript", "")
            re_verify_results = masker_data.get("re_verify_results", [])
            
            if not transcript:
                logger.warning("No transcript found in masker_data")
                return {
                    "status": "failed",
                    "error": "No transcript found",
                    "masked_transcript": "",
                    "masking_summary": {}
                }
            
            # Parse transcript to structured format if needed
            if isinstance(transcript, str):
                transcript_data = parse_transcription(transcript)
                transcript_data = transcript_data.get("transcript", transcript_data)
            else:
                transcript_data = transcript
            
            # Chunk transcript with same parameters as usecase (60s with 10s overlap)
            logger.debug("Chunking transcript with 60s windows and 10s overlap")
            chunked_result = chunk_transcript(
                json_data=transcript_data,
                chunk_duration=60.0,
                overlap_duration=10.0,
                include_original_text=True
            )
            
            # Extract PASS detections from re_verify_results
            pass_detections = self._extract_pass_detections(re_verify_results)
            logger.info(f"Found {len(pass_detections)} PASS detections for masking")
            
            # Map detections to chunks based on timestamps
            chunk_detections_map = self._map_detections_to_chunks(
                pass_detections, 
                chunked_result["chunks"]
            )
            
            # Process each chunk with masker workflow
            masked_chunks = []
            total_detections_masked = 0
            semaphore = asyncio.Semaphore(9)
            
            async def process_chunk_with_masker(chunk):
                async with semaphore:
                    chunk_id = chunk["metadata"]["chunk_index"]
                    detections = chunk_detections_map.get(chunk_id, [])
                    
                    if not detections:
                        return {
                            "chunk_id": chunk_id,
                            "masked_text": chunk.get("text", ""),
                            "detections_masked": 0,
                            "status": "skipped_no_detections"
                        }
                    
                    transcript_text = chunk.get("text", "")
                    metadata = chunk.get("metadata", {})
                    
                    try:
                        masker_input = {
                            "detection_data": {
                                "transcript_text": transcript_text,
                                "detections": detections,
                                "metadata": metadata
                            },
                            "masker_results": {}
                        }
                        
                        # Execute masker workflow
                        logger.debug(f"Processing chunk {chunk_id} with {len(detections)} detections")
                        masker_result = await self._workflow.ainvoke(masker_input)
                        
                        # Extract results - check multiple possible result formats
                        masker_results_list = masker_result.get("masker_results", [])
                        
                        # Try to extract masked transcript from masker_results
                        masked_text = chunk.get("text", "")  # Default to original text
                        
                        if masker_results_list and len(masker_results_list) > 0:
                            # Get the first result from masker_results
                            first_result = masker_results_list[0]
                            
                            # Check if the result contains transcript
                            if "transcript" in first_result:
                                masked_text = first_result.get("transcript", chunk.get("text", ""))
                                logger.debug(f"Found masked transcript in masker_results for chunk {chunk_id}")
                                logger.debug(f"Original text length: {len(chunk.get('text', ''))}, Masked text length: {len(masked_text)}")
                            else:
                                logger.warning(f"No transcript found in masker_results for chunk {chunk_id}")
                                logger.debug(f"Available keys in masker result: {list(first_result.keys())}")
                        else:
                            logger.warning(f"No masker_results found for chunk {chunk_id}")
                            
                        # Debug logging to verify masking
                        if masked_text == chunk.get("text", "") and len(detections) > 0:
                            logger.warning(f"Chunk {chunk_id} has {len(detections)} detections but text was not masked!")
                        elif len(detections) > 0:
                            logger.debug(f"Chunk {chunk_id} successfully masked {len(detections)} detections")
                        
                        # Debug logging to verify masking
                        if masked_text == chunk.get("text", "") and len(detections) > 0:
                            logger.warning(f"Chunk {chunk_id} has {len(detections)} detections but text was not masked!")
                        elif len(detections) > 0:
                            logger.debug(f"Chunk {chunk_id} successfully masked {len(detections)} detections")
                        
                        return {
                            "chunk_id": chunk_id,
                            "masked_text": masked_text,
                            "detections_masked": len(detections),
                            "masker_results": masker_results_list,
                            "status": "success"
                        }
                        
                    except Exception as e:
                        logger.error(f"Masker workflow failed for chunk {chunk_id}: {e}")
                        # Return original text on failure
                        return {
                            "chunk_id": chunk_id,
                            "masked_text": chunk.get("text", ""),
                            "detections_masked": 0,
                            "status": "failed",
                            "error": str(e)
                        }
            
            # Process all chunks
            tasks = [process_chunk_with_masker(chunk) for chunk in chunked_result["chunks"]]
            if tasks:
                masked_chunks = await asyncio.gather(*tasks)
                total_detections_masked = sum(chunk.get("detections_masked", 0) for chunk in masked_chunks)
            
            # Reconstruct full transcript from masked chunks
            masked_transcript = self._reconstruct_transcript(masked_chunks, chunked_result["chunks"])
            
            # Create summary
            processed_chunks = sum(1 for chunk in masked_chunks if chunk.get("status") == "success")
            skipped_chunks = sum(1 for chunk in masked_chunks if chunk.get("status") == "skipped_no_detections")
            failed_chunks = sum(1 for chunk in masked_chunks if chunk.get("status") == "failed")
            
            masking_summary = {
                "total_chunks": len(chunked_result["chunks"]),
                "processed_chunks": processed_chunks,
                "skipped_chunks": skipped_chunks,
                "failed_chunks": failed_chunks,
                "total_detections_masked": total_detections_masked,
                "chunking_config": chunked_result["chunking_config"]
            }
            
            logger.info(f"Masker processing completed: {total_detections_masked} detections masked across {processed_chunks} chunks")
            
            return {
                "status": "success",
                "masked_transcript": masked_transcript,
                "masking_summary": masking_summary,
                # "masked_chunks": masked_chunks
            }
            
        except Exception as e:
            logger.error(f"Masker action failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "masked_transcript": "",
                "masking_summary": {}
            }
    
    def _extract_pass_detections(self, re_verify_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract only PASS detections from re-verify results"""
        pass_detections = []
        
        for result in re_verify_results:
            re_verify_result = result.get("re_verify_result", {})
            
            logger.debug(f"Processing re-verify result: {re_verify_result}")

            # Check if recommendation is PASS
            if re_verify_result.get("recommendation") == "PASS":
                # Convert to masker input format
                detection = {
                    "id": result.get("detection_id", ""),
                    "type": result.get("detection_type", ""),
                    "original_text": result.get("original_text", ""),
                    "start_time": result.get("start_time", 0),
                    "end_time": result.get("end_time", 0),
                    "verification_status": "PASS",
                    "likely_category": re_verify_result.get("likely_category", ""),
                    "reasoning": re_verify_result.get("reasoning", ""),
                    "confidence": re_verify_result.get("confidence", 0)
                }
                pass_detections.append(detection)

        return pass_detections
    
    def _map_detections_to_chunks(self, detections: List[Dict[str, Any]], chunks: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
        """Map detections to chunks based on timestamps"""
        chunk_map = {chunk["metadata"]["chunk_index"]: [] for chunk in chunks}
        
        for detection in detections:
            det_start = detection.get("start_time", 0)
            det_end = detection.get("end_time", 0)
            
            # Find all chunks that overlap with this detection
            for chunk in chunks:
                chunk_start = chunk["metadata"]["chunk_start"]
                chunk_end = chunk["metadata"]["chunk_end"]
                
                # Check if detection overlaps with chunk
                if det_start < chunk_end and det_end > chunk_start:
                    chunk_id = chunk["metadata"]["chunk_index"]
                    chunk_map[chunk_id].append(detection)
        
        return chunk_map
    
    def _reconstruct_transcript(self, masked_chunks: List[Dict[str, Any]], original_chunks: List[Dict[str, Any]]) -> str:
        """Reconstruct the full transcript from masked chunks"""
        # Create a mapping of chunk_id to masked chunk data
        chunk_map = {chunk["chunk_id"]: chunk for chunk in masked_chunks}
        
        # Process all original chunks in order
        all_chunks_text = []
        for original_chunk in original_chunks:
            chunk_id = original_chunk["metadata"]["chunk_index"]
            
            # Get the masked chunk if available, otherwise use original
            masked_chunk = chunk_map.get(chunk_id)
            if masked_chunk and masked_chunk.get("status") == "success":
                # Use masked text if masking was successful
                chunk_text = masked_chunk.get("masked_text", original_chunk.get("text", ""))
            else:
                # Use original text if chunk was skipped or failed
                chunk_text = original_chunk.get("text", "")
            
            all_chunks_text.append(chunk_text)
        
        # Join all chunks with newlines
        masked_transcript = "\n".join(all_chunks_text)
        
        return masked_transcript