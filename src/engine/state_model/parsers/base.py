"""Base Parser Interface - Abstract interface for language parsers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParsedSymbol:
    """A symbol extracted by a parser."""
    
    name: str
    kind: str
    file_path: str
    line_start: int
    line_end: int
    
    signature: str = ""
    docstring: str = ""
    
    bases: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    
    qualified_name: str = ""
    module_path: str = ""
    
    is_async: bool = False
    is_override: bool = False
    is_test: bool = False
    is_static: bool = False
    
    # Calls made by this symbol
    calls: list[str] = field(default_factory=list)


@dataclass
class ParsedImport:
    """An import statement."""
    
    module_path: str
    imported_names: list[str] = field(default_factory=list)
    alias: str | None = None
    is_wildcard: bool = False
    is_relative: bool = False
    level: int = 0
    line: int = 0


@dataclass
class ParseResult:
    """Result of parsing a source file."""
    
    file_path: str
    language: str
    
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    
    module_path: str = ""
    exports: list[str] = field(default_factory=list)
    
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BaseParser(ABC):
    """Abstract base class for language-specific parsers."""
    
    # Override in subclasses
    language: str = ""
    extensions: tuple[str, ...] = ()
    
    @abstractmethod
    def parse(self, file_path: str | Path, content: str | None = None) -> ParseResult:
        """Parse a source file and extract symbols.
        
        Args:
            file_path: Path to the source file
            content: Optional file content (if None, read from file_path)
            
        Returns:
            ParseResult containing extracted symbols and imports
        """
        pass
    
    @abstractmethod
    def get_symbol_qualified_name(
        self,
        symbol: ParsedSymbol,
        module_path: str,
    ) -> str:
        """Get the fully qualified name for a symbol."""
        pass
    
    def can_parse(self, file_path: str | Path) -> bool:
        """Check if this parser can handle the file."""
        path = Path(file_path)
        return any(path.suffix == ext for ext in self.extensions)
    
    def extract_calls_from_signature(self, signature: str) -> list[str]:
        """Extract function/class names from a signature."""
        import re
        # Match function/class names in typical call patterns
        pattern = r'\b([A-Z][a-zA-Z0-9_]*)\s*\('
        matches = re.findall(pattern, signature)
        return [m for m in matches if m not in ('self', 'cls', 'type')]
    
    def is_test_name(self, name: str) -> bool:
        """Check if a symbol name looks like a test."""
        return (
            name.startswith('test_') or
            name.endswith('_test') or
            name.startswith('Test') or
            name.endswith('Test') or
            name.startswith('test') or
            'test' in name.lower()
        )


def get_parser_for_language(language: str) -> type[BaseParser] | None:
    """Get the appropriate parser for a language."""
    from .python_parser import PythonParser
    
    parsers = {
        'python': PythonParser,
        'py': PythonParser,
        'pyw': PythonParser,
    }
    
    return parsers.get(language.lower())


def get_parser_for_extension(extension: str) -> type[BaseParser] | None:
    """Get the appropriate parser for a file extension."""
    from .python_parser import PythonParser
    
    parser_map = {
        '.py': PythonParser,
        '.pyw': PythonParser,
        '.pyi': PythonParser,
    }
    
    return parser_map.get(extension.lower())
