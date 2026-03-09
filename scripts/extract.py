"""Extract production code from Jupyter notebooks via @export tags."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
NOTEBOOKS_DIR = ROOT / "notebooks"

NOTEBOOK_MAP = {
    "01_transcript_fetch.ipynb": "src/transcript.py",
    "02_chunking.ipynb": "src/chunking.py",
    "03_pinecone_operations.ipynb": "src/vectorstore.py",
    "04_claude_tools.ipynb": "src/tools.py",
    "05_agent_routing.ipynb": "src/agent.py",
}


def extract_notebook(nb_path: Path) -> dict[str, list[str]]:
    """Return {target_file: [cell_source, ...]} for all @export cells."""
    nb = json.loads(nb_path.read_text())
    targets: dict[str, list[str]] = {}

    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        raw_source = cell.get("source", [])
        if not raw_source:
            continue
        # Handle both list-of-lines and single-string formats
        if isinstance(raw_source, str):
            source_lines = raw_source.splitlines(keepends=True)
        else:
            source_lines = raw_source
        if not source_lines:
            continue
        first = source_lines[0].strip()
        m = re.match(r"#\s*@export\s+(\S+)", first)
        if not m:
            continue
        target = m.group(1)
        # Strip the @export line itself
        body = "".join(source_lines[1:])
        targets.setdefault(target, []).append(body)

    return targets


def collect_imports(source: str) -> tuple[list[str], str]:
    """Split source into (import_lines, rest).

    Handles multi-line imports with parentheses, e.g.:
        from foo import (
            Bar,
            Baz,
        )
    """
    import_lines = []
    rest_lines = []
    in_multiline = False
    current_import: list[str] = []

    for line in source.splitlines(keepends=True):
        stripped = line.strip()

        if in_multiline:
            current_import.append(line)
            if ")" in line:
                import_lines.extend(current_import)
                current_import = []
                in_multiline = False
        elif not line[0:1].isspace() and (stripped.startswith("import ") or stripped.startswith("from ")):
            if "(" in line and ")" not in line:
                # Opening of a multi-line import
                in_multiline = True
                current_import = [line]
            else:
                import_lines.append(line)
        else:
            rest_lines.append(line)

    # Shouldn't happen, but flush any unclosed import
    if current_import:
        import_lines.extend(current_import)

    return import_lines, "".join(rest_lines)


def deduplicate_imports(import_lines: list[str]) -> list[str]:
    seen = set()
    result = []
    for line in import_lines:
        key = line.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(line)
    return result


def write_module(target: str, cells: list[str]):
    out_path = ROOT / target
    out_path.parent.mkdir(parents=True, exist_ok=True)

    all_imports: list[str] = []
    all_rest: list[str] = []

    for cell in cells:
        imports, rest = collect_imports(cell)
        all_imports.extend(imports)
        all_rest.append(rest)

    unique_imports = deduplicate_imports(all_imports)

    header = '"""Auto-generated from notebooks. Do not edit directly."""\n\n'
    content = header + "".join(unique_imports) + "\n\n" + "\n\n".join(all_rest)

    out_path.write_text(content)
    print(f"  wrote {target}")


def main():
    for nb_name in NOTEBOOK_MAP:
        nb_path = NOTEBOOKS_DIR / nb_name
        if not nb_path.exists():
            print(f"  MISSING: {nb_path}")
            continue
        targets = extract_notebook(nb_path)
        for target, cells in targets.items():
            write_module(target, cells)


if __name__ == "__main__":
    main()
