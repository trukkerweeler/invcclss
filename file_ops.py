"""File operations for invoice renaming."""

import os


def rename_file(original_path, suffix):
    """Rename file by prepending suffix to the original filename.

    Args:
        original_path: Full path to the original file
        suffix: Prefix to add before the filename (e.g., '2024-01_Supplier')

    Returns:
        str: Full path to the renamed file
    """
    folder, original_name = os.path.split(original_path)
    base, ext = os.path.splitext(original_name)
    new_name = f"{suffix}_{base}{ext}" if suffix else f"{base}{ext}"
    new_path = os.path.join(folder, new_name)
    os.rename(original_path, new_path)
    return new_path
