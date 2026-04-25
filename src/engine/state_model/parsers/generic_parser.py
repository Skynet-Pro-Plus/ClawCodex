"""Generic Parser - Fallback parser for unsupported languages."""

from __future__ import annotations

import re
from pathlib import Path

from .base import BaseParser, ParseResult, ParsedImport, ParsedSymbol


class GenericParser(BaseParser):
    """Fallback parser using regex patterns for symbol extraction.
    
    This parser is used when a language-specific parser is not available.
    It uses simple regex patterns to find function/class definitions.
    """
    
    language = "generic"
    extensions = (".txt",)
    
    def __init__(self):
        self._function_pattern = re.compile(
            r'^(?:export\s+)?(?:function|def|fn|func)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            re.MULTILINE
        )
        self._class_pattern = re.compile(
            r'^(?:export\s+)?(?:class|struct|interface|type)\s+([A-Z][a-zA-Z0-9_]*)',
            re.MULTILINE
        )
        self._import_pattern = re.compile(
            r'^(?:import|from|require|use)\s+([^\s;]+)',
            re.MULTILINE
        )
    
    def parse(self, file_path: str | Path, content: str | None = None) -> ParseResult:
        """Parse a file using regex patterns."""
        path = Path(file_path)
        
        if content is None:
            try:
                content = path.read_text(encoding='utf-8')
            except Exception as e:
                return ParseResult(
                    file_path=str(path),
                    language=self.language,
                    errors=[f"Failed to read file: {e}"],
                )
        
        symbols = []
        imports = []
        exports = []
        
        # Find functions
        for match in self._function_pattern.finditer(content):
            name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            symbols.append(ParsedSymbol(
                name=name,
                kind="function",
                file_path=str(path),
                line_start=line_num,
                line_end=line_num,
                is_test=self.is_test_name(name),
            ))
        
        # Find classes
        for match in self._class_pattern.finditer(content):
            name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            symbols.append(ParsedSymbol(
                name=name,
                kind="class",
                file_path=str(path),
                line_start=line_num,
                line_end=line_num,
                is_test=self.is_test_name(name),
            ))
        
        # Find imports
        for match in self._import_pattern.finditer(content):
            module_path = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            
            imports.append(ParsedImport(
                module_path=module_path,
                line=line_num,
            ))
        
        return ParseResult(
            file_path=str(path),
            language="generic",
            symbols=symbols,
            imports=imports,
            exports=exports,
        )
    
    def get_symbol_qualified_name(
        self,
        symbol: ParsedSymbol,
        module_path: str,
    ) -> str:
        """Get the fully qualified name."""
        if symbol.qualified_name:
            return symbol.qualified_name
        
        if module_path:
            return f"{module_path}.{symbol.name}"
        return symbol.name
