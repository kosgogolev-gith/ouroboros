import os
import re
import tempfile
from pathlib import Path
import ast

from ouroboros.llm import LLMClient
from ouroboros.tools.memory import chat_history_tool, update_scratchpad_tool
from ouroboros.tools.search import web_search_tool
from ouroboros.tools.git import git_status_tool, git_diff_tool
from ouroboros.tools.repo import repo_read_tool, repo_list_tool
from ouroboros.tools.drive import drive_read_tool, drive_list_tool, drive_write_tool
from ouroboros.tools.internal import send_owner_message_tool, request_restart_tool, update_identity_tool, schedule_task_tool, get_task_result_tool, wait_for_task_tool, promote_to_stable_tool
from ouroboros.tools.code import claude_code_edit_tool
from ouroboros.tools.shell import run_shell_tool
from ouroboros.tools.knowledge import knowledge_read_tool, knowledge_write_tool

# Constants for test_no_extremely_oversized_functions
MAX_FUNCTION_LINES = 150
MAX_FUNCTION_PARAMS = 8

def test_imports():
    """Verify that essential modules can be imported without errors."""
    assert LLMClient is not None, "LLMClient should be importable"
    assert chat_history_tool is not None, "chat_history_tool should be importable"
    assert web_search_tool is not None, "web_search_tool should be importable"

def test_ollama_client_init():
    """Ensure LLMClient can be initialized without crashing."""
    try:
        client = LLMClient()
        assert client is not None, "LLMClient should be initialized"
    except Exception as e:
        assert False, f"LLMClient initialization failed: {e}"

def test_memory_chat_history_empty():
    """Verify chat history can be retrieved, even if empty."""
    # Use a temporary directory for memory files
    with tempfile.TemporaryDirectory() as tmpdir:
        original_drive_root = os.environ.get("DRIVE_ROOT")
        os.environ["DRIVE_ROOT"] = tmpdir
        try:
            Path(tmpdir).mkdir(parents=True, exist_ok=True)
            result = chat_history_tool(count=1)
            assert isinstance(result, dict), "chat_history should return a dictionary"
            assert "messages" in result, "chat_history result should contain 'messages'"
            assert len(result["messages"]) == 0, "Initially, chat history should be empty"
        finally:
            if original_drive_root:
                os.environ["DRIVE_ROOT"] = original_drive_root
            else:
                del os.environ["DRIVE_ROOT"]


def test_scratchpad_update():
    """Ensure scratchpad can be updated."""
    test_content = "This is a test scratchpad entry."
    # Use a temporary directory for memory files
    with tempfile.TemporaryDirectory() as tmpdir:
        original_drive_root = os.environ.get("DRIVE_ROOT")
        os.environ["DRIVE_ROOT"] = tmpdir
        try:
            Path(tmpdir).mkdir(parents=True, exist_ok=True)
            result = update_scratchpad_tool(content=test_content)
            assert isinstance(result, dict), "update_scratchpad should return a dictionary"
            assert "message" in result, "update_scratchpad result should contain 'message'"
            assert "success" in result["message"], "update_scratchpad success message expected"

            # Verify content by reading it
            with open(Path(tmpdir) / "memory" / "scratchpad.md", "r") as f:
                read_content = f.read()
            assert read_content == test_content, "Scratchpad content should match what was written"
        finally:
            if original_drive_root:
                os.environ["DRIVE_ROOT"] = original_drive_root
            else:
                del os.environ["DRIVE_ROOT"]


def test_no_hardcoded_replies():
    """Ensure no hardcoded 'I am a bot' or similar in prompts/SYSTEM.md."""
    system_prompt_path = Path("prompts/SYSTEM.md")
    if not system_prompt_path.exists():
        assert False, f"prompts/SYSTEM.MD not found at {system_prompt_path.absolute()}"

    content = system_prompt_path.read_text()
    assert not re.search(r"I am a (bot|service|assistant)\.?", content, re.IGNORECASE), \
        "SYSTEM.MD should not contain hardcoded 'I am a bot/service/assistant' replies."

def test_no_extremely_oversized_functions():
    """
    Checks for functions that exceed MAX_FUNCTION_LINES or MAX_FUNCTION_PARAMS in the codebase.
    This helps enforce Principle 5: Minimalism, by encouraging decomposition and readability.
    """
    repo_root = Path(__file__).parent.parent
    violations = []

    for file_path in repo_root.glob("ouroboros/**/*.py"):
        if "ouroboros/tools" in str(file_path):
            continue  # Skip tools for this specific check, they might be larger by design

        try:
            tree = ast.parse(file_path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    function_name = node.name
                    lines = node.body[-1].lineno - node.body[0].lineno + 1 if node.body else 0
                    params = len(node.args.args)

                    if lines > MAX_FUNCTION_LINES:
                        violations.append(
                            f"{file_path.relative_to(repo_root)}:{function_name} "
                            f"exceeds {MAX_FUNCTION_LINES} lines ({lines} lines)"
                        )
                    if params > MAX_FUNCTION_PARAMS:
                        violations.append(
                            f"{file_path.relative_to(repo_root)}:{function_name} "
                            f"exceeds {MAX_FUNCTION_PARAMS} parameters ({params} params)"
                        )
        except SyntaxError:
            violations.append(f"SyntaxError in {file_path.relative_to(repo_root)}")
        except Exception as e:
            violations.append(f"Error processing {file_path.relative_to(repo_root)}: {e}")

    assert len(violations) == 0, \
        f"Codebase contains oversized functions or methods:\\n" + "\\n".join(violations)

def test_function_count_reasonable():
    """
    Checks the total number of functions and methods in the codebase.
    This helps ensure overall codebase complexity remains manageable.
    """
    repo_root = Path(__file__).parent.parent
    function_count = 0
    parse_errors = []

    for file_path in repo_root.glob("ouroboros/**/*.py"):
        if "ouroboros/tools" in str(file_path):
            continue  # Skip tools, as they might have many small functions

        try:
            tree = ast.parse(file_path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    function_count += 1
        except SyntaxError:
            parse_errors.append(f"SyntaxError in {file_path.relative_to(repo_root)}")
        except Exception as e:
            parse_errors.append(f"Error processing {file_path.relative_to(repo_root)}: {e}")

    assert not parse_errors, f"Errors encountered during parsing:\\n" + "\\n".join(parse_errors)
    assert function_count <= 400, f"Too many functions ({function_count}): consider refactoring or consolidating."
