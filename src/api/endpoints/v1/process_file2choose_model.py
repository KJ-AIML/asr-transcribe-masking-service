import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from src.config.logs_config import get_logger
from src.execution.actions.process_file2choose_model_action import (
    ProcessFile2ChooseModelAction,
)
from src.execution.usecases.process_file2choose_model_usecase import (
    ProcessFile2ChooseModelUseCase,
)

router = APIRouter()
logger = get_logger(__name__)


class ModelSelectionResponse(BaseModel):
    """Response model for model selection processing"""

    message: str
    filename: str
    model_selection_results: Dict[str, Any]
    processing_status: str
    json_file_path: str


# Dependency injection
async def get_process_file2choose_model_usecase() -> ProcessFile2ChooseModelUseCase:
    action = ProcessFile2ChooseModelAction()
    return ProcessFile2ChooseModelUseCase(action)


@router.post(
    "/process_file2choose_model",
    status_code=status.HTTP_200_OK,
    response_model=ModelSelectionResponse,
)
async def process_file2choose_model(
    file: UploadFile = File(..., description="JSON file containing chunk_dict data"),
    usecase: ProcessFile2ChooseModelUseCase = Depends(
        get_process_file2choose_model_usecase
    ),
):
    """
    Process JSON file containing chunk_dict for ASR model selection

    Args:
        file: JSON file containing chunk_dict data

    Returns:
        ModelSelectionResponse: Processing status and model selection results
    """
    try:
        # Validate file type
        if not file.filename.endswith(".json"):
            raise ValueError("Only .json files are supported")

        logger.info(f"Received JSON file: {file.filename}")

        # Read and parse JSON file content
        file_content = await file.read()
        json_data = json.loads(file_content.decode("utf-8"))

        if not isinstance(json_data, dict):
            raise ValueError("JSON file must contain a valid JSON object")

        # Extract filename from JSON data or use the uploaded filename
        filename = json_data.get("filename", file.filename.replace(".json", ""))

        # Process JSON data through usecase
        result = await usecase.execute(json_data, filename)

        return ModelSelectionResponse(
            message="Model selection completed successfully",
            filename=result["filename"],
            model_selection_results=result["model_selection"],
            processing_status=result["processing_stage"],
            json_file_path=result.get("json_file_path", ""),
        )

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON file: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Error processing JSON for model selection: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing model selection: {str(e)}",
        )
