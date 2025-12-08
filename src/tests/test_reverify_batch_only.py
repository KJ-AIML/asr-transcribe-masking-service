"""
Test script for re-running Re-verify Batch process on already processed data
This allows testing Re-verify Batch without running the full processing pipeline
"""

import json
import asyncio
import os
from typing import Dict, List, Any

from src.execution.actions.process_transcript_reverify_action import ProcessTranscriptReVerifyAction
from src.utils.re_verify.context_extraction import prepare_batch_re_verify_input
from src.config.logs_config import get_logger

logger = get_logger(__name__)

class ReVerifyBatchTester:
    def __init__(self):
        self.re_verify_action = ProcessTranscriptReVerifyAction()
        
    async def test_reverify_batch_on_processed_file(
        self, 
        processed_file_path: str,
        original_files_dir: str,
        output_file_path: str = None
    ) -> Dict[str, Any]:
        """
        Test Re-verify Batch process on already processed file
        
        Args:
            processed_file_path: Path to processed JSON file
            original_files_dir: Directory containing original transcript files
            output_file_path: Optional path to save results
            
        Returns:
            Dictionary containing test results
        """
        logger.info(f"Starting Re-verify Batch test on {processed_file_path}")
        
        # Load processed data
        with open(processed_file_path, 'r', encoding='utf-8') as f:
            processed_data = json.load(f)
        
        results = []
        
        # Process each file in the processed data
        for file_entry in processed_data:
            filename, file_data = file_entry
            
            logger.info(f"Processing file: {filename}")
            
            # Load original transcript for context
            original_file_path = os.path.join(original_files_dir, filename)
            if not os.path.exists(original_file_path):
                logger.warning(f"Original file not found: {original_file_path}")
                continue
                
            with open(original_file_path, 'r', encoding='utf-8') as f:
                original_transcript = json.load(f)
            
            # Find chunks with credit cards
            credit_card_chunks = [
                chunk for chunk in file_data["processed_chunks"]
                if chunk.get("has_credit_card", False)
            ]
            
            logger.info(f"Found {len(credit_card_chunks)} chunks with credit cards")
            
            # Process each credit card chunk as a batch with concurrent processing
            re_verify_semaphore = asyncio.Semaphore(9)
            
            async def process_chunk_batch(i, chunk):
                async with re_verify_semaphore:
                    return await self._process_chunk_with_reverify_batch(
                        chunk, 
                        original_transcript,
                        filename
                    )
            
            chunk_tasks = [process_chunk_batch(i, chunk) for i, chunk in enumerate(credit_card_chunks)]
            if chunk_tasks:
                chunk_results = await asyncio.gather(*chunk_tasks)
            else:
                chunk_results = []
            
            # Compile results for this file
            file_result = {
                "filename": filename,
                "total_chunks": file_data["total_chunks"],
                "chunks_with_credit_card": file_data["chunks_with_credit_card"],
                "reverify_batch_results": chunk_results,
                "summary": self._generate_summary(chunk_results)
            }
            
            results.append(file_result)
        
        # Save results if output path provided
        if output_file_path:
            with open(output_file_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"Results saved to {output_file_path}")
        
        return {
            "status": "success",
            "total_files": len(results),
            "results": results
        }
    
    async def _process_chunk_with_reverify_batch(
        self, 
        chunk: Dict[str, Any], 
        original_transcript: Dict[str, Any],
        filename: str
    ) -> Dict[str, Any]:
        """
        Process a single chunk with Re-verify Batch
        
        Args:
            chunk: Chunk data from processed file
            original_transcript: Original transcript data
            filename: Original filename
            
        Returns:
            Dictionary containing Re-verify Batch results for this chunk
        """
        chunk_id = chunk["chunk_id"]
        logger.info(f"Processing chunk {chunk_id} from {filename} with Batch Re-verify")
        
        # Get masked credit cards from original processing
        original_masked_cards = chunk.get("masked_credit_cards", [])
        
        # Convert to detections format for batch processing
        detections = []
        for card in original_masked_cards:
            detection = {
                "id": card.get("id", f"det_{len(detections)}"),
                "type": card["type"],
                "original_text": card["original_text"],
                "masked_text": card.get("masked_text", ""),
                "start_time": card["start_time"],
                "end_time": card["end_time"],
                "segment_ids": card.get("segment_ids", []),
                "confidence": card["confidence"],
                "category": card.get("category", "")
            }
            detections.append(detection)
        
        # Prepare batch input with context
        batch_input = prepare_batch_re_verify_input(
            chunk, 
            detections, 
            original_transcript
        )
        
        # Debug: Log what we're sending to Batch Re-verify
        logger.info(f"Sending to Batch Re-verify - Chunk {chunk_id}")
        logger.info(f"Number of detections: {len(detections)}")
        logger.info(f"Context text length: {len(batch_input.get('context_text', ''))}")
        logger.info(f"Segments count: {len(batch_input.get('segments', []))}")
        
        # Execute Batch Re-verify
        batch_result = await self.re_verify_action.execute(batch_input)
        
        # Map results back to individual detections
        mapped_results = []
        results_list = batch_result.get("re_verify_results", [])
        
        # Handle nested results structure (from workflow)
        actual_results = []
        for item in results_list:
            if isinstance(item, dict) and "results" in item:
                actual_results.extend(item["results"])
            else:
                actual_results.append(item)
        
        # Create a map for quick lookup using detection_id
        results_map = {r.get("detection_id"): r for r in actual_results}
        
        for detection in detections:
            det_id = detection["id"]
            result_data = results_map.get(det_id, {"status": "error", "error": "Missing from batch result"})
            
            mapped_results.append({
                "detection_id": det_id,
                "detection_type": detection["type"],
                "original_text": detection["original_text"],
                "masked_text": detection.get("masked_text", ""),
                "start_time": detection.get("start_time"),
                "end_time": detection.get("end_time"),
                "re_verify_result": result_data,
                "chunk_id": chunk_id
            })
        
        return {
            "chunk_id": chunk_id,
            "timestamp_range": chunk["timestamp_range"],
            "original_masked_cards": original_masked_cards,
            "batch_reverify_results": mapped_results,
            "summary": self._generate_chunk_summary(original_masked_cards, mapped_results)
        }
    
    def _generate_summary(self, chunk_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary statistics for all chunks"""
        total_cards = 0
        passed_reverify = 0
        failed_reverify = 0
        
        for chunk in chunk_results:
            total_cards += len(chunk["batch_reverify_results"])
            for result in chunk["batch_reverify_results"]:
                re_verify_result = result.get("re_verify_result", {})
                if re_verify_result.get("recommendation") == "PASS":
                    passed_reverify += 1
                else:
                    failed_reverify += 1
        
        return {
            "total_cards": total_cards,
            "passed_reverify": passed_reverify,
            "failed_reverify": failed_reverify,
            "pass_rate": passed_reverify / total_cards if total_cards > 0 else 0
        }
    
    def _generate_chunk_summary(
        self, 
        original_cards: List[Dict[str, Any]], 
        batch_reverify_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate summary for a single chunk"""
        passed = sum(1 for r in batch_reverify_results 
                    if r.get("re_verify_result", {}).get("recommendation") == "PASS")
        failed = len(batch_reverify_results) - passed
        
        return {
            "total_cards": len(original_cards),
            "passed_reverify": passed,
            "failed_reverify": failed,
            "pass_rate": passed / len(batch_reverify_results) if batch_reverify_results else 0
        }

async def main():
    """Main function to run Re-verify Batch test"""
    tester = ReVerifyBatchTester()
    
    # File paths
    processed_file = "d:/Terrabit/asr_service_server/examples/processed_sample_test_set.json"
    original_files_dir = "d:/Terrabit/asr_service_server/examples/sample_test_set"
    output_file = "d:/Terrabit/asr_service_server/examples/reverify_batch_test_results.json"
    
    # Run test
    results = await tester.test_reverify_batch_on_processed_file(
        processed_file,
        original_files_dir,
        output_file
    )
    
    # Print summary
    print("\n=== Re-Verify Batch Test Results ===")
    print(f"Total files processed: {results['total_files']}")
    
    for file_result in results["results"]:
        filename = file_result["filename"]
        summary = file_result["summary"]
        print(f"\nFile: {filename}")
        print(f"  Total cards: {summary['total_cards']}")
        print(f"  Passed Re-verify: {summary['passed_reverify']}")
        print(f"  Failed Re-verify: {summary['failed_reverify']}")
        print(f"  Pass Rate: {summary['pass_rate']:.2%}")

if __name__ == "__main__":
    asyncio.run(main())