"""Generate comprehensive function documentation from source code."""

import ast
import inspect
from pathlib import Path
from typing import Dict, List
import importlib.util


def extract_docstrings(file_path: Path) -> Dict[str, Dict]:
    """Extract all functions and classes with their docstrings from a Python file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    tree = ast.parse(content)
    docs = {}
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            docstring = ast.get_docstring(node)
            
            # Get function signature
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in node.args.args]
                if node.args.vararg:
                    args.append(f"*{node.args.vararg.arg}")
                if node.args.kwarg:
                    args.append(f"**{node.args.kwarg.arg}")
                signature = f"{name}({', '.join(args)})"
            else:
                signature = name
            
            docs[name] = {
                'type': 'function' if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else 'class',
                'signature': signature,
                'docstring': docstring or "No docstring available",
                'file': str(file_path.relative_to(Path.cwd())),
            }
    
    return docs


def generate_documentation() -> str:
    """Generate comprehensive documentation from all Python files."""
    scraper_dir = Path(__file__).parent.parent / "scrapers"
    docs = {}
    
    # Find all Python files
    for py_file in scraper_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        
        file_docs = extract_docstrings(py_file)
        if file_docs:
            rel_path = str(py_file.relative_to(scraper_dir.parent))
            docs[rel_path] = file_docs
    
    # Generate markdown
    output = "# Function Documentation\n\n"
    output += "Auto-generated documentation from source code.\n\n"
    
    for file_path, file_docs in sorted(docs.items()):
        output += f"## {file_path}\n\n"
        
        for name, info in sorted(file_docs.items()):
            output += f"### `{info['signature']}`\n\n"
            output += f"**Type:** {info['type']}\n\n"
            output += f"**File:** `{info['file']}`\n\n"
            output += f"**Documentation:**\n\n{info['docstring']}\n\n"
            output += "---\n\n"
    
    return output


if __name__ == "__main__":
    docs = generate_documentation()
    output_file = Path(__file__).parent.parent / "FUNCTION_DOCS.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(docs)
    print(f"Documentation generated: {output_file}")

