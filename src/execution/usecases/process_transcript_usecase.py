from typing import Dict, Any
import asyncio
from src.config.logs_config import get_logger
from src.execution.actions.process_transcript_action import ProcessTranscriptAction
from src.execution.actions.process_transcript_reverify_action import (
    ProcessTranscriptReVerifyAction,
)
from src.execution.actions.process_transcript_masker_action import (
    ProcessTranscriptMaskerAction,
)
from src.utils.transcript.chunk_transcript import chunk_transcript
from src.utils.transcript.prase_transcript import parse_transcription
from src.utils.re_verify.timestamp_extraction import extract_detections_by_chunk
from src.utils.re_verify.context_extraction import prepare_batch_re_verify_input

logger = get_logger(__name__)


class ProcessTranscriptUseCase:
    def __init__(
        self,
        action: ProcessTranscriptAction,
        re_verify_action: ProcessTranscriptReVerifyAction = None,
        masker_action: ProcessTranscriptMaskerAction = None,
    ):
        self.action = action
        self.re_verify_action = re_verify_action
        self.masker_action = masker_action

    async def execute(self, transcript_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process transcript for credit card detection"""
        logger.info("Starting transcript processing")

        # ถ้าเป็น raw text ให้ parse ก่อน
        if isinstance(transcript_data, str):
            text_length = len(transcript_data)
            line_count = transcript_data.count("\n") + 1
            logger.info(
                f"UseCase received raw text: {text_length} chars, {line_count} lines"
            )

            # Log first and last lines for debugging
            lines = transcript_data.split("\n")
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
                    logger.info(
                        f"First segment: [{first_seg['start']} --> {first_seg['end']}] [{first_seg['channel']}]: {first_seg['text'][:50]}..."
                    )
                    logger.info(
                        f"Last segment: [{last_seg['start']} --> {last_seg['end']}] [{last_seg['channel']}]: {last_seg['text'][:50]}..."
                    )

        # Chunk transcript 100 วินาที
        logger.debug("Chunking transcript with 100s windows")
        chunked_result = chunk_transcript(
            json_data=transcript_data,
            chunk_duration=60.0,
            overlap_duration=5.0,
            include_original_text=True,
        )

        # Process each chunk
        processed_chunks = []
        semaphore = asyncio.Semaphore(9)

        async def process_single_chunk(chunk):
            async with semaphore:
                chunk_id = chunk["metadata"]["chunk_index"]
                retries = 1
                base_delay = 3.0

                for attempt in range(retries + 1):
                    try:
                        logger.debug(
                            f"Processing chunk {chunk_id} (Attempt {attempt + 1})"
                        )

                        # ส่งเข้า workflow
                        workflow_result = await self.action.execute(chunk)

                        # เช็คผลลัพธ์
                        has_credit_card = self._has_credit_card_data(workflow_result)

                        # Always store workflow_result for Payment Agent detection extraction
                        subagent_response = workflow_result.get("subagent_response", {})

                        if has_credit_card:
                            # Extract masked credit cards from the new structure
                            masking_results = subagent_response.get(
                                "masking_results", []
                            )

                            return {
                                "chunk_id": chunk_id,
                                "has_credit_card": True,
                                "status": "credit_card_found",
                                "masked_credit_cards": masking_results,
                                "summary": subagent_response.get("summary", {}),
                                "timestamp_range": {
                                    "start": chunk["metadata"]["chunk_start"],
                                    "end": chunk["metadata"]["chunk_end"],
                                },
                                "workflow_result": workflow_result,  # Store for Payment Agent detection extraction
                            }
                        else:
                            return {
                                "chunk_id": chunk_id,
                                "has_credit_card": False,
                                "status": "no_credit_card_found",
                                "timestamp_range": {
                                    "start": chunk["metadata"]["chunk_start"],
                                    "end": chunk["metadata"]["chunk_end"],
                                },
                                "workflow_result": workflow_result,  # Store for Payment Agent detection extraction
                            }

                    except Exception as e:
                        if attempt < retries:
                            delay = base_delay * (2**attempt)
                            logger.warning(
                                f"Chunk {chunk_id} failed (Attempt {attempt + 1}/{retries + 1}): {str(e)}. Retrying in {delay}s..."
                            )
                            await asyncio.sleep(delay)
                        else:
                            logger.error(
                                f"Chunk {chunk_id} failed after {retries + 1} attempts: {str(e)}"
                            )
                            # Return a failed result structure instead of crashing everything
                            return {
                                "chunk_id": chunk_id,
                                "has_credit_card": False,
                                "status": "failed",
                                "error": str(e),
                                "timestamp_range": {
                                    "start": chunk["metadata"]["chunk_start"],
                                    "end": chunk["metadata"]["chunk_end"],
                                },
                                "workflow_result": {},
                            }

        tasks = [process_single_chunk(chunk) for chunk in chunked_result["chunks"]]
        if tasks:
            processed_chunks = await asyncio.gather(*tasks)
            # Sort by chunk_id to maintain order
            processed_chunks.sort(key=lambda x: x["chunk_id"])

            # Check for failed chunks and retry them
            failed_chunks = [c for c in processed_chunks if c.get("status") == "failed"]
            if failed_chunks:
                logger.warning(f"Found {len(failed_chunks)} failed chunks, retrying...")

                # Retry failed chunks with a higher retry count
                async def retry_failed_chunk(chunk_result):
                    chunk_id = chunk_result["chunk_id"]
                    # Find the original chunk data
                    original_chunk = next(
                        c
                        for c in chunked_result["chunks"]
                        if c["metadata"]["chunk_index"] == chunk_id
                    )

                    retries = 3
                    base_delay = 5.0

                    for attempt in range(retries):
                        try:
                            logger.info(
                                f"Retrying failed chunk {chunk_id} (Attempt {attempt + 1}/{retries})"
                            )

                            # ส่งเข้า workflow
                            workflow_result = await self.action.execute(original_chunk)

                            # เช็คผลลัพธ์
                            has_credit_card = self._has_credit_card_data(
                                workflow_result
                            )

                            # Always store workflow_result for Payment Agent detection extraction
                            subagent_response = workflow_result.get(
                                "subagent_response", {}
                            )

                            if has_credit_card:
                                # Extract masked credit cards from the new structure
                                masking_results = subagent_response.get(
                                    "masking_results", []
                                )

                                return {
                                    "chunk_id": chunk_id,
                                    "has_credit_card": True,
                                    "status": "credit_card_found",
                                    "masked_credit_cards": masking_results,
                                    "summary": subagent_response.get("summary", {}),
                                    "timestamp_range": {
                                        "start": original_chunk["metadata"][
                                            "chunk_start"
                                        ],
                                        "end": original_chunk["metadata"]["chunk_end"],
                                    },
                                    "workflow_result": workflow_result,
                                }
                            else:
                                return {
                                    "chunk_id": chunk_id,
                                    "has_credit_card": False,
                                    "status": "no_credit_card_found",
                                    "timestamp_range": {
                                        "start": original_chunk["metadata"][
                                            "chunk_start"
                                        ],
                                        "end": original_chunk["metadata"]["chunk_end"],
                                    },
                                    "workflow_result": workflow_result,
                                }

                        except Exception as e:
                            if attempt < retries - 1:
                                delay = base_delay * (2**attempt)
                                logger.warning(
                                    f"Retry chunk {chunk_id} failed (Attempt {attempt + 1}/{retries}): {str(e)}. Retrying in {delay}s..."
                                )
                                await asyncio.sleep(delay)
                            else:
                                logger.error(
                                    f"Retry chunk {chunk_id} failed after {retries} attempts: {str(e)}"
                                )
                                # Return the original failed result
                                return chunk_result

                # Process retries with semaphore to control concurrency
                retry_semaphore = asyncio.Semaphore(3)
                retry_tasks = []

                async def process_with_semaphore(chunk_result):
                    async with retry_semaphore:
                        return await retry_failed_chunk(chunk_result)

                retry_tasks = [process_with_semaphore(c) for c in failed_chunks]
                if retry_tasks:
                    retry_results = await asyncio.gather(*retry_tasks)

                    # Replace failed chunks with retry results
                    for retry_result in retry_results:
                        for i, chunk in enumerate(processed_chunks):
                            if chunk["chunk_id"] == retry_result["chunk_id"]:
                                processed_chunks[i] = retry_result
                                break

                    # Sort again to maintain order
                    processed_chunks.sort(key=lambda x: x["chunk_id"])

                    # Log retry summary
                    successful_retries = sum(
                        1 for c in failed_chunks if c.get("status") != "failed"
                    )
                    logger.info(
                        f"Successfully retried {successful_retries}/{len(failed_chunks)} chunks"
                    )

        # สรุมผล
        result = {
            "total_chunks": len(processed_chunks),
            "chunks_with_credit_card": sum(
                1 for c in processed_chunks if c["has_credit_card"]
            ),
            "processed_chunks": processed_chunks,
            "chunking_info": chunked_result["chunking_config"],
            "processing_summary": {
                "total_duration": chunked_result["chunking_config"]["total_duration"],
                "chunk_size": 60.0,
                "overlap": 5.0,
            },
        }

        # Check for chunks with failed workflow_result before Batch Re-Verify
        failed_workflow_chunks = []
        for chunk in processed_chunks:
            if chunk.get("workflow_result", {}).get("status") == "failed":
                failed_workflow_chunks.append(chunk)

        if failed_workflow_chunks:
            logger.warning(
                f"Found {len(failed_workflow_chunks)} chunks with failed workflow but credit card detected, retrying..."
            )

            # Retry failed workflow chunks with higher retry count
            async def retry_failed_workflow_chunk(chunk):
                chunk_id = chunk["chunk_id"]
                # Find the original chunk data
                original_chunk = next(
                    c
                    for c in chunked_result["chunks"]
                    if c["metadata"]["chunk_index"] == chunk_id
                )

                retries = 5
                base_delay = 5.0

                for attempt in range(retries):
                    try:
                        logger.info(
                            f"Retrying failed workflow chunk {chunk_id} (Attempt {attempt + 1}/{retries})"
                        )

                        # ส่งเข้า workflow
                        workflow_result = await self.action.execute(original_chunk)

                        # Check if workflow failed (status == "failed")
                        if workflow_result.get("status") == "failed":
                            error_msg = workflow_result.get("error", "Unknown error")
                            raise Exception(f"Workflow execution failed: {error_msg}")

                        # เช็คผลลัพธ์
                        has_credit_card = self._has_credit_card_data(workflow_result)

                        # Always store workflow_result for Payment Agent detection extraction
                        subagent_response = workflow_result.get("subagent_response", {})

                        if has_credit_card:
                            # Extract masked credit cards from the new structure
                            masking_results = subagent_response.get(
                                "masking_results", []
                            )

                            return {
                                "chunk_id": chunk_id,
                                "has_credit_card": True,
                                "status": "credit_card_found",
                                "masked_credit_cards": masking_results,
                                "summary": subagent_response.get("summary", {}),
                                "timestamp_range": {
                                    "start": original_chunk["metadata"]["chunk_start"],
                                    "end": original_chunk["metadata"]["chunk_end"],
                                },
                                "workflow_result": workflow_result,
                            }
                        else:
                            return {
                                "chunk_id": chunk_id,
                                "has_credit_card": False,
                                "status": "no_credit_card_found",
                                "timestamp_range": {
                                    "start": original_chunk["metadata"]["chunk_start"],
                                    "end": original_chunk["metadata"]["chunk_end"],
                                },
                                "workflow_result": workflow_result,
                            }

                    except Exception as e:
                        if attempt < retries - 1:
                            delay = base_delay * (2**attempt)
                            logger.warning(
                                f"Retry workflow chunk {chunk_id} failed (Attempt {attempt + 1}/{retries}): {str(e)}. Retrying in {delay}s..."
                            )
                            await asyncio.sleep(delay)
                        else:
                            logger.error(
                                f"Retry workflow chunk {chunk_id} failed after {retries} attempts: {str(e)}"
                            )
                            # Return the original failed result
                            return chunk

            # Process retries with semaphore to control concurrency
            retry_semaphore = asyncio.Semaphore(3)
            retry_tasks = []

            async def process_with_semaphore(chunk):
                async with retry_semaphore:
                    return await retry_failed_workflow_chunk(chunk)

            retry_tasks = [process_with_semaphore(c) for c in failed_workflow_chunks]
            if retry_tasks:
                retry_results = await asyncio.gather(*retry_tasks)

                # Replace failed chunks with retry results
                for retry_result in retry_results:
                    for i, chunk in enumerate(processed_chunks):
                        if chunk["chunk_id"] == retry_result["chunk_id"]:
                            processed_chunks[i] = retry_result
                            break

                # Update result statistics
                result["chunks_with_credit_card"] = sum(
                    1 for c in processed_chunks if c["has_credit_card"]
                )

                # Log retry summary
                successful_retries = sum(
                    1
                    for c in retry_results
                    if c.get("workflow_result", {}).get("status") != "failed"
                )
                logger.info(
                    f"Successfully retried {successful_retries}/{len(failed_workflow_chunks)} workflow chunks"
                )

        # Re-Verify process (if re_verify_action is provided)
        re_verify_results = []
        if self.re_verify_action and result["chunks_with_credit_card"] > 0:
            logger.info("Starting Batch Re-Verify process")

            # Extract detections grouped by chunk
            chunks_with_detections = extract_detections_by_chunk(processed_chunks)
            logger.info(
                f"Found {len(chunks_with_detections)} chunks with detections for Batch Re-Verify"
            )

            # Process each chunk as a batch
            re_verify_semaphore = asyncio.Semaphore(9)

            async def process_batch_reverify(i, chunk_data):
                async with re_verify_semaphore:
                    retries = 5
                    base_delay = 3.0
                    chunk_id = chunk_data["chunk_id"]

                    for attempt in range(retries):
                        try:
                            logger.info(
                                f"Processing batch chunk {chunk_id} ({len(chunk_data['detections'])} detections) (Attempt {attempt + 1}/{retries})"
                            )

                            # Prepare batch input
                            batch_input = prepare_batch_re_verify_input(
                                chunk_data["chunk_data"],
                                chunk_data["detections"],
                                transcript_data,
                            )

                            # logger.info(f"Batch Re-Verify input: {batch_input}")

                            # Execute batch re-verify workflow
                            batch_result = await self.re_verify_action.execute(
                                batch_input
                            )

                            # Check if re-verify failed and trigger retry
                            if batch_result.get("status") == "failed":
                                raise Exception(
                                    f"Re-verify workflow failed: {batch_result.get('error', 'Unknown error')}"
                                )

                            logger.info(
                                f"Batch Re-Verify completed for chunk {chunk_id}"
                            )

                            # Map results back to individual detections structure for compatibility
                            mapped_results = []
                            results_list = batch_result.get("re_verify_results", [])

                            # Handle nested results structure (from workflow)
                            # The results might be nested under "results" key
                            actual_results = []
                            for item in results_list:
                                if isinstance(item, dict) and "results" in item:
                                    actual_results.extend(item["results"])
                                else:
                                    actual_results.append(item)

                            # Create a map for quick lookup using detection_id
                            results_map = {
                                r.get("detection_id"): r for r in actual_results
                            }

                            for detection in chunk_data["detections"]:
                                det_id = detection["id"]
                                result_data = results_map.get(
                                    det_id,
                                    {
                                        "status": "error",
                                        "error": "Missing from batch result",
                                    },
                                )

                                mapped_results.append(
                                    {
                                        "detection_id": det_id,
                                        "detection_type": detection["type"],
                                        "original_text": detection["original_text"],
                                        "start_time": detection.get("start_time"),
                                        "end_time": detection.get("end_time"),
                                        "re_verify_result": result_data,
                                        "chunk_id": chunk_id,
                                    }
                                )

                            return mapped_results

                        except Exception as e:
                            if attempt < retries - 1:
                                delay = base_delay * (2**attempt)
                                logger.warning(
                                    f"Batch Re-Verify chunk {chunk_id} failed (Attempt {attempt + 1}/{retries}): {str(e)}. Retrying in {delay}s..."
                                )
                                await asyncio.sleep(delay)
                            else:
                                logger.error(
                                    f"Batch Re-Verify failed for chunk {chunk_id} after {retries} attempts: {str(e)}"
                                )
                                # Return error results for all detections in this chunk
                                return [
                                    {
                                        "detection_id": d["id"],
                                        "detection_type": d["type"],
                                        "original_text": d["original_text"],
                                        "re_verify_result": {"error": str(e)},
                                        "chunk_id": chunk_id,
                                    }
                                    for d in chunk_data["detections"]
                                ]

            re_verify_tasks = [
                process_batch_reverify(i, c)
                for i, c in enumerate(chunks_with_detections)
            ]
            if re_verify_tasks:
                batch_results_list = await asyncio.gather(*re_verify_tasks)
                # Flatten the list of lists
                for batch in batch_results_list:
                    re_verify_results.extend(batch)

        # Deduplicate re-verify results by timestamp (from overlapping chunks)
        def deduplicate_detections(detections):
            """Remove duplicate detections based on timestamp and text"""
            seen = set()
            unique = []
            for det in detections:
                # Create unique key from start_time, end_time, and original_text
                key = (
                    det.get("start_time"),
                    det.get("end_time"),
                    det.get("original_text", ""),
                )
                if key not in seen:
                    seen.add(key)
                    unique.append(det)
                else:
                    logger.debug(
                        f"Removing duplicate detection: {det.get('original_text', '')} at {det.get('start_time')}-{det.get('end_time')}"
                    )
            return unique

        # Apply deduplication
        original_count = len(re_verify_results)
        re_verify_results = deduplicate_detections(re_verify_results)
        if original_count != len(re_verify_results):
            logger.info(
                f"Deduplicated re-verify results: {original_count} -> {len(re_verify_results)}"
            )

        # Add re-verify results to the main result
        result["re_verify_results"] = re_verify_results
        result["re_verify_summary"] = {
            "total_detections": sum(
                len(c["detections"]) for c in chunks_with_detections
            )
            if "chunks_with_detections" in locals()
            else 0,
            "processed_detections": len(re_verify_results),
            "successful_re_verifies": sum(
                1
                for r in re_verify_results
                if "error" not in r.get("re_verify_result", {})
            ),
        }

        logger.info(
            f"Processing complete: {result['chunks_with_credit_card']}/{result['total_chunks']} chunks contain credit cards"
        )
        logger.info(
            f"Re-Verify complete: {result['re_verify_summary']['successful_re_verifies']}/{result['re_verify_summary']['processed_detections']} detections processed"
        )

        # # Process each chunk as a batch
        # # Masker process
        # if (
        #     self.masker_action
        #     and result["re_verify_summary"]["processed_detections"] > 0
        # ):
        #     logger.info("Starting Masker process for re-verified detections")

        # # Prepare input for masker action
        # masker_input = {
        #     "transcript": transcript_data.get("text", ""),
        #     "re_verify_results": result["re_verify_results"],
        # }

        # # Execute masker action
        # masker_result = await self.masker_action.execute(masker_input)

        # # Add masker results to final result
        # result["masker_result"] = masker_result
        # result["original_transcript"] = transcript_data.get("text", "")
        # result["masked_transcript"] = masker_result.get("masked_transcript", "")
        # result["masker_summary"] = masker_result.get("masking_summary", {})

        # logger.info(
        #     f"Masker process completed: {result['masker_summary'].get('total_detections_masked', 0)} detections masked"
        # )

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
                if category != "No Card" and category in [
                    "Success Mask",
                    "Success Partial",
                ]:
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
                            logger.info(
                                f"Found Payment Agent detection: {detection.get('value', 'N/A')}"
                            )
                            return True

        return False
