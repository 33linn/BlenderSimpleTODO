"""Ensure that the package contains only files required by the extension."""

from pathlib import Path
from zipfile import ZipFile


project_dir = Path(__file__).resolve().parents[1]
zip_path = project_dir / "dist" / "todo_list-1.0.0.zip"

expected_files = {
    "__init__.py",
    "blender_manifest.toml",
    "LICENSE",
}

with ZipFile(zip_path) as archive:
    packaged_files = {
        name
        for name in archive.namelist()
        if not name.endswith("/")
    }

assert packaged_files == expected_files, packaged_files
assert not any(name.startswith(("docs/", "tests/")) for name in packaged_files)
assert "README.md" not in packaged_files
print("SIMPLE_TODO_PACKAGE_OK")
