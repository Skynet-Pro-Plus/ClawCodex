"""Python Parser - AST-based Python source code parser."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any

from .base import BaseParser, ParseResult, ParsedImport, ParsedSymbol


class PythonParser(BaseParser):
    """Parser for Python source files using the ast module."""
    
    language = "python"
    extensions = (".py", ".pyw", ".pyi")
    
    def parse(self, file_path: str | Path, content: str | None = None) -> ParseResult:
        """Parse a Python file and extract symbols."""
        path = Path(file_path)
        
        if content is None:
            try:
                content = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                try:
                    content = path.read_text(encoding='latin-1')
                except Exception as e:
                    return ParseResult(
                        file_path=str(path),
                        language=self.language,
                        errors=[f"Failed to read file: {e}"],
                    )
        
        module_path = self._get_module_path(path)
        
        try:
            tree = ast.parse(content, filename=str(path))
        except SyntaxError as e:
            return ParseResult(
                file_path=str(path),
                language=self.language,
                errors=[f"Syntax error at line {e.lineno}: {e.msg}"],
            )
        
        visitor = PythonVisitor(str(path), module_path, content)
        visitor.visit(tree)
        
        return ParseResult(
            file_path=str(path),
            language=self.language,
            symbols=visitor.symbols,
            imports=visitor.imports,
            module_path=module_path,
            exports=visitor.exports,
            errors=visitor.errors,
            warnings=visitor.warnings,
        )
    
    def get_symbol_qualified_name(
        self,
        symbol: ParsedSymbol,
        module_path: str,
    ) -> str:
        """Get the fully qualified name for a Python symbol."""
        if symbol.qualified_name:
            return symbol.qualified_name
        
        if module_path:
            return f"{module_path}.{symbol.name}"
        return symbol.name
    
    def _get_module_path(self, path: Path) -> str:
        """Extract module path from file path."""
        parts = path.parts
        # Find common patterns like 'src', 'lib', or package root
        for i, part in enumerate(parts):
            if part in ('src', 'lib', 'app', 'apps'):
                return '.'.join(parts[i+1:])
        
        # Fallback: use parent directories
        if len(parts) >= 2:
            return '.'.join(parts[-2:])
        return parts[-1] if parts else ''


class PythonVisitor(ast.NodeVisitor):
    """AST visitor that extracts symbols and imports."""
    
    def __init__(self, file_path: str, module_path: str, content: str):
        self.file_path = file_path
        self.module_path = module_path
        self.content = content
        self.lines = content.split('\n')
        
        self.symbols: list[ParsedSymbol] = []
        self.imports: list[ParsedImport] = []
        self.exports: list[str] = []
        
        self.errors: list[str] = []
        self.warnings: list[str] = []
        
        self._class_stack: list[str] = []
        self._in_async_def = False
    
    def visit(self, node: ast.AST) -> Any:
        """Override visit to track async state."""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            old_async = self._in_async_def
            self._in_async_def = isinstance(node, ast.AsyncFunctionDef)
            super().visit(node)
            self._in_async_def = old_async
        else:
            super().visit(node)
    
    def visit_Module(self, node: ast.Module) -> None:
        """Extract module-level exports (__all__)."""
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == '__all__':
                        try:
                            self.exports = [
                                elt.value if isinstance(elt, ast.Constant) else elt.s
                                for elt in item.value.elts
                            ]
                        except Exception:
                            pass
        self.generic_visit(node)
    
    def visit_Import(self, node: ast.Import) -> None:
        """Handle regular imports."""
        imported_names = [alias.name for alias in node.names]
        imp = ParsedImport(
            module_path=imported_names[0].split('.')[0],
            imported_names=imported_names,
            line=node.lineno,
        )
        self.imports.append(imp)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Handle 'from X import Y' imports."""
        if node.level > 0:
            module_parts = ['..'] * node.level + [node.module or '']
        else:
            module_parts = [node.module or '']
        
        imported_names = [alias.asname or alias.name for alias in node.names]
        is_wildcard = any(alias.name == '*' for alias in node.names)
        
        imp = ParsedImport(
            module_path='.'.join(filter(None, module_parts)),
            imported_names=imported_names,
            is_wildcard=is_wildcard,
            is_relative=node.level > 0,
            level=node.level,
            line=node.lineno,
        )
        self.imports.append(imp)
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Extract function definitions."""
        self._visit_function(node, is_async=isinstance(node, ast.AsyncFunctionDef))
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Extract async function definitions."""
        self._visit_function(node, is_async=True)
    
    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        is_async: bool = False,
    ) -> None:
        """Extract function/method definition."""
        name = node.name
        
        # Skip private methods if inside class
        if name.startswith('_') and self._class_stack:
            return
        
        # Determine symbol kind
        kind = "function"
        if self._class_stack:
            kind = "method"
        
        # Build qualified name
        if self._class_stack:
            class_name = self._class_stack[-1]
            qualified_name = f"{self.module_path}.{class_name}.{name}" if self.module_path else f"{class_name}.{name}"
        else:
            qualified_name = f"{self.module_path}.{name}" if self.module_path else name
        
        # Extract decorators
        decorators = []
        for decorator in node.decorator_list:
            decorators.append(self._get_decorator_name(decorator))
        
        # Check for override
        is_override = 'override' in decorators or any(
            self._get_decorator_name(d) == 'abstractmethod'
            for d in decorators
        )
        
        # Get signature
        signature = self._get_function_signature(node)
        
        # Get docstring
        docstring = ast.get_docstring(node) or ""
        
        # Get calls from function body
        calls = self._extract_calls(node)
        
        symbol = ParsedSymbol(
            name=name,
            kind=kind,
            file_path=self.file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            signature=signature,
            docstring=docstring,
            decorators=decorators,
            qualified_name=qualified_name,
            module_path=self.module_path,
            is_async=is_async,
            is_override=is_override,
            is_test=self.is_test_name(name) or name.startswith('test_'),
            calls=calls,
        )
        
        self.symbols.append(symbol)
        self.generic_visit(node)
    
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Extract class definitions."""
        name = node.name
        
        # Get base classes
        bases = []
        for base in node.bases:
            base_name = self._get_name_from_expr(base)
            if base_name:
                bases.append(base_name)
        
        # Extract decorators
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]
        
        # Get docstring
        docstring = ast.get_docstring(node) or ""
        
        # Build qualified name
        qualified_name = f"{self.module_path}.{name}" if self.module_path else name
        
        symbol = ParsedSymbol(
            name=name,
            kind="class",
            file_path=self.file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            signature=self._get_class_signature(bases),
            docstring=docstring,
            bases=bases,
            decorators=decorators,
            qualified_name=qualified_name,
            module_path=self.module_path,
            is_test=self.is_test_name(name),
            calls=self._extract_calls(node),
        )
        
        self.symbols.append(symbol)
        
        # Track class context
        self._class_stack.append(name)
        self.generic_visit(node)
        self._class_stack.pop()
    
    def visit_Assign(self, node: ast.Assign) -> None:
        """Extract module-level constants."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                name = target.name
                
                # Only capture constants (ALL_CAPS)
                if name.isupper() and not name.startswith('_'):
                    symbol = ParsedSymbol(
                        name=name,
                        kind="constant",
                        file_path=self.file_path,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        qualified_name=f"{self.module_path}.{name}" if self.module_path else name,
                        module_path=self.module_path,
                    )
                    self.symbols.append(symbol)
        
        self.generic_visit(node)
    
    def _get_decorator_name(self, decorator: ast.expr) -> str:
        """Get the name of a decorator."""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Attribute):
            return decorator.attr
        elif isinstance(decorator, ast.Call):
            return self._get_decorator_name(decorator.func)
        return ""
    
    def _get_function_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Build a signature string for a function."""
        args = node.args
        
        # Get argument names
        arg_names = []
        
        # Handle self/cls
        if args.args:
            first_arg = args.args[0]
            if first_arg.arg in ('self', 'cls'):
                arg_names.append(first_arg.arg)
                args = ast.arguments(
                    posonlyargs=args.posonlyargs[1:] if args.posonlyargs else [],
                    args=args.args[1:],
                    kwonlyargs=args.kwonlyargs,
                    defaults=args.defaults[1:] if args.defaults else [],
                    kw_defaults=args.kw_defaults[1:] if args.kw_defaults else [],
                    annotations=args.annotations[1:] if args.annotations else [],
                )
            else:
                arg_names.extend(a.arg for a in args.args)
        else:
            # Handle posonlyargs
            posonly = [a.arg for a in args.posonlyargs]
            arg_names.extend(posonly)
        
        # Add kwonly args
        arg_names.extend(a.arg for a in args.kwonlyargs)
        
        # Build signature
        sig_parts = [node.name, '(']
        
        for i, arg in enumerate(arg_names):
            if i > 0:
                sig_parts.append(', ')
            sig_parts.append(arg)
            
            # Check for default value
            defaults_offset = len(arg_names) - len(args.defaults)
            if i >= defaults_offset:
                default_idx = i - defaults_offset
                if default_idx < len(args.defaults):
                    sig_parts.append('=')
                    sig_parts.append(self._get_default_value(args.defaults[default_idx]))
        
        sig_parts.append(')')
        
        # Add return type hint
        if args.annotations and isinstance(args.annotations[-1], ast.Constant):
            ret_type = args.annotations[-1].value
            if ret_type:
                sig_parts.append(f' -> {ret_type}')
        
        return ''.join(sig_parts)
    
    def _get_class_signature(self, bases: list[str]) -> str:
        """Build a signature for a class."""
        if bases:
            return f"class {bases[0]}"
        return "class"
    
    def _get_default_value(self, default: ast.expr) -> str:
        """Get string representation of a default value."""
        if isinstance(default, ast.Constant):
            if isinstance(default.value, str):
                return f'"{default.value}"'
            return repr(default.value)
        elif isinstance(default, ast.Name):
            return default.id
        elif isinstance(default, ast.Attribute):
            return f"{self._get_name_from_expr(default)}"
        return "..."
    
    def _get_name_from_expr(self, expr: ast.expr) -> str:
        """Extract name from an expression."""
        if isinstance(expr, ast.Name):
            return expr.id
        elif isinstance(expr, ast.Attribute):
            base = self._get_name_from_expr(expr.value)
            return f"{base}.{expr.attr}" if base else expr.attr
        elif isinstance(expr, ast.Constant):
            return str(expr.value)
        return ""
    
    def _extract_calls(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
        """Extract function/class calls from a function body."""
        calls = []
        
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    name = self._get_name_from_expr(child.func)
                    if name:
                        calls.append(name)
        
        return list(set(calls))
