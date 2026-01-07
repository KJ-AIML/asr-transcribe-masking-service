import json
import os
from typing import Any, Dict, Optional


def save_result_to_json(
    data: Dict[str, Any], filename: str, directory: Optional[str] = None
) -> str:
    """
    Save processing results to a JSON file.

    Args:
        data: Dictionary data to save as JSON
        filename: Base filename (without .json extension)
        directory: Target directory path (defaults to src/data/wav2files)

    Returns:
        Full path to the created JSON file

    Raises:
        OSError: If directory creation fails
        IOError: If file writing fails
    """
    if directory is None:
        # Default path relative to project root
        directory = os.path.join("src", "data", "wav2files")

    # Create directory if it doesn't exist
    os.makedirs(directory, exist_ok=True)

    # Create the full file path with .json extension
    file_path = os.path.join(directory, f"{filename}.json")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return file_path
    except Exception as e:
        raise IOError(f"Failed to save JSON data to {file_path}: {str(e)}")


def load_json_file(file_path: str) -> Dict[str, Any]:
    """
    Load data from a JSON file.

    Args:
        file_path: Path to the JSON file

    Returns:
        Dictionary containing the JSON data

    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the file contains invalid JSON
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_json_directory_exists(directory: Optional[str] = None) -> str:
    """
    Ensure the JSON data directory exists.

    Args:
        directory: Directory path to create (defaults to src/data/wav2files)

    Returns:
        Path to the created/existing directory
    """
    if directory is None:
        directory = os.path.join("src", "data", "wav2files")

    os.makedirs(directory, exist_ok=True)
    return directory
