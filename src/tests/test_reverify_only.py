"""
Test script for re-running Re-verify process on already processed data
This allows testing Re-verify without running the full processing pipeline
"""

import json
import asyncio
import os
from typing import Dict, List, Any

from src.execution.actions.process_transcript_reverify_action import (
    ProcessTranscriptReVerifyAction,
)
from src.utils.re_verify.context_extraction import prepare_re_verify_input
from src.config.logs_config import get_logger

logger = get_logger(__name__)


class ReVerifyTester:
    def __init__(self):
        self.re_verify_action = ProcessTranscriptReVerifyAction()

    async def test_reverify_on_processed_file(
        self,
        processed_file_path: str,
        original_files_dir: str,
        output_file_path: str = None,
    ) -> Dict[str, Any]:
        """
        Test Re-verify process on already processed file

        Args:
            processed_file_path: Path to processed JSON file
            original_files_dir: Directory containing original transcript files
            output_file_path: Optional path to save results

        Returns:
            Dictionary containing test results
        """
        logger.info(f"Starting Re-verify test on {processed_file_path}")

        # Load processed data
        with open(processed_file_path, "r", encoding="utf-8") as f:
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

            with open(original_file_path, "r", encoding="utf-8") as f:
                original_transcript = json.load(f)

            # Find chunks with credit cards
            credit_card_chunks = [
                chunk
                for chunk in file_data["processed_chunks"]
                if chunk.get("has_credit_card", False)
            ]

            logger.info(f"Found {len(credit_card_chunks)} chunks with credit cards")

            # Process each credit card chunk
            chunk_results = []
            for chunk in credit_card_chunks:
                chunk_result = await self._process_chunk_with_reverify(
                    chunk, original_transcript, filename
                )
                chunk_results.append(chunk_result)

            # Compile results for this file
            file_result = {
                "filename": filename,
                "total_chunks": file_data["total_chunks"],
                "chunks_with_credit_card": file_data["chunks_with_credit_card"],
                "reverify_results": chunk_results,
                "summary": self._generate_summary(chunk_results),
            }

            results.append(file_result)

        # Save results if output path provided
        if output_file_path:
            with open(output_file_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"Results saved to {output_file_path}")

        return {"status": "success", "total_files": len(results), "results": results}

    async def _process_chunk_with_reverify(
        self, chunk: Dict[str, Any], original_transcript: Dict[str, Any], filename: str
    ) -> Dict[str, Any]:
        """
        Process a single chunk with Re-verify

        Args:
            chunk: Chunk data from processed file
            original_transcript: Original transcript data
            filename: Original filename

        Returns:
            Dictionary containing Re-verify results for this chunk
        """
        chunk_id = chunk["chunk_id"]
        logger.info(f"Processing chunk {chunk_id} from {filename}")

        # Get masked credit cards from original processing
        original_masked_cards = chunk.get("masked_credit_cards", [])

        # Re-verify each detection
        reverify_results = []
        for card in original_masked_cards:
            # Create detection object for Re-verify
            detection = {
                "detection": {
                    "type": card["type"],
                    "start_time": card["start_time"],
                    "end_time": card["end_time"],
                    "text": card["original_text"],
                    "confidence": card["confidence"],
                }
            }

            # Prepare Re-verify input with context
            reverify_input = prepare_re_verify_input(detection, original_transcript)

            # Debug: Log what we're sending to Re-verify
            logger.info(
                f"Sending to Re-verify - Detection: {detection['detection']['text']}"
            )
            logger.info(
                f"Context text length: {len(reverify_input.get('context_text', ''))}"
            )
            logger.info(f"Segments count: {len(reverify_input.get('segments', []))}")

            # Execute Re-verify
            reverify_result = await self.re_verify_action.execute(reverify_input)

            # Add original card info for comparison
            reverify_result["original_card"] = card
            reverify_results.append(reverify_result)

        return {
            "chunk_id": chunk_id,
            "timestamp_range": chunk["timestamp_range"],
            "original_masked_cards": original_masked_cards,
            "reverify_results": reverify_results,
            "summary": self._generate_chunk_summary(
                original_masked_cards, reverify_results
            ),
        }

    def _generate_summary(self, chunk_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary statistics for all chunks"""
        total_cards = 0
        passed_reverify = 0
        failed_reverify = 0

        for chunk in chunk_results:
            total_cards += len(chunk["reverify_results"])
            for result in chunk["reverify_results"]:
                if result.get("verified_detection"):
                    passed_reverify += 1
                else:
                    failed_reverify += 1

        return {
            "total_cards": total_cards,
            "passed_reverify": passed_reverify,
            "failed_reverify": failed_reverify,
            "pass_rate": passed_reverify / total_cards if total_cards > 0 else 0,
        }

    def _generate_chunk_summary(
        self,
        original_cards: List[Dict[str, Any]],
        reverify_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate summary for a single chunk"""
        passed = sum(1 for r in reverify_results if r.get("verified_detection"))
        failed = len(reverify_results) - passed

        return {
            "total_cards": len(original_cards),
            "passed_reverify": passed,
            "failed_reverify": failed,
            "pass_rate": passed / len(reverify_results) if reverify_results else 0,
        }


async def main():
    """Main function to run Re-verify test"""
    tester = ReVerifyTester()

    # File paths
    processed_file = (
        "d:/Terrabit/asr_service_server/examples/processed_sample_test_set_v6.json"
    )
    original_files_dir = "d:/Terrabit/asr_service_server/examples/sample_test_set"
    output_file = "d:/Terrabit/asr_service_server/examples/reverify_test_results.json"

    # Run test
    results = await tester.test_reverify_on_processed_file(
        processed_file, original_files_dir, output_file
    )

    # Print summary
    print("\n=== Re-Verify Test Results ===")
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
