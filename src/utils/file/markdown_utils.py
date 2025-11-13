from charset_normalizer import from_path
import textwrap

def read_markdown_file_with_dedent(file_path: str, dedent: bool = True) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        try:
            result = from_path(file_path).best()
            if result is None:
                return f"Error: Could not detect encoding for {file_path}"
            text = str(result)
        except Exception as e:
            return f"An error occurred during encoding detection: {e}"
    except FileNotFoundError:
        return f"Error: File not found at {file_path}"
    except Exception as e:
        return f"An error occurred: {e}"

    return textwrap.dedent(text) if dedent else text