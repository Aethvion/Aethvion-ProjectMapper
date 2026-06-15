"""
project_mapper.analyzers
Language extractors for the scanner.

`base` holds the shared types (CodeAnalysis, ImportInfo), the language
dispatcher (analyze_file), and language detection (detect_language_for_path).
Every other module is a single-language extractor (one file per language).
"""
from .base import (
    CodeAnalysis,
    ImportInfo,
    analyze_file,
    detect_language_for_path,
)

__all__ = [
    "CodeAnalysis",
    "ImportInfo",
    "analyze_file",
    "detect_language_for_path",
]
