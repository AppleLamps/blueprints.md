"""Compact blueprint parser module for extracting information from .md files."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field


@dataclass
class Method:
    """Represents a method or function signature."""
    name: str
    params: str
    return_type: Optional[str] = None
    comment: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    is_async: bool = False


@dataclass
class Component:
    """Represents a component (class, function, etc.) in a blueprint."""
    type: str  # "class", "function", "constant", "type_alias"
    name: str
    base_class: Optional[str] = None
    methods: List[Method] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)
    value: Optional[str] = None  # For constants and type aliases
    docstring: Optional[str] = None


@dataclass
class BlueprintReference:
    """Represents a reference to another blueprint."""
    module_path: str
    items: List[str] = field(default_factory=list)


@dataclass
class Blueprint:
    """Represents a parsed compact blueprint file."""
    module_name: str
    description: str = ""
    blueprint_refs: List[BlueprintReference] = field(default_factory=list)  # references to other blueprints
    components: List[Component] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    raw_content: str = ""
    file_path: Optional[Path] = None


class CompactBlueprintParser:
    """Parses compact blueprint markdown files into structured data."""
    
    def parse_file(self, file_path: Path) -> Blueprint:
        """Parse a blueprint file and return structured data."""
        content = file_path.read_text()
        blueprint = self.parse_content(content)
        blueprint.file_path = file_path
        return blueprint
    
    def parse_content(self, content: str) -> Blueprint:
        """Parse compact blueprint content and return structured data."""
        lines = content.strip().split('\n')
        
        # Extract module name and description from first two lines
        if not lines or not lines[0].startswith('#'):
            raise ValueError("Blueprint must start with # module.name")
        
        module_name = lines[0].strip('#').strip()
        description = lines[1].strip() if len(lines) > 1 else ""
        
        blueprint = Blueprint(
            module_name=module_name,
            description=description,
            raw_content=content
        )
        
        # Parse the rest of the content
        i = 2
        while i < len(lines):
            line = lines[i].strip()
            
            if line.startswith('deps:'):
                # Parse only blueprint references (ignore standard/3rd party deps)
                deps_str = line[5:].strip()
                refs = self._parse_blueprint_refs(deps_str)
                blueprint.blueprint_refs = refs
                i += 1
                
            elif line.startswith('notes:'):
                # Parse notes
                notes_str = line[6:].strip()
                blueprint.notes = [n.strip() for n in notes_str.split(',')]
                i += 1
                
            elif line and not line.startswith('#'):
                # Parse component
                component = self._parse_component(lines, i)
                if component:
                    blueprint.components.append(component)
                    # Skip lines that belong to this component
                    i = self._find_component_end(lines, i) + 1
                else:
                    i += 1
            else:
                i += 1
        
        return blueprint
    
    def _parse_blueprint_refs(self, deps_str: str) -> List[BlueprintReference]:
        """Parse only blueprint references from dependency string."""
        blueprint_refs = []
        
        # Split by semicolon for different dependencies
        for dep in deps_str.split(';'):
            dep = dep.strip()
            if not dep:
                continue
            
            # Only process blueprint references (starting with @ or .)
            if dep.startswith('.') or dep.startswith('@'):
                # Check if it has items in brackets
                if '[' in dep and ']' in dep:
                    package = dep[:dep.index('[')].strip()
                    items_str = dep[dep.index('[')+1:dep.index(']')]
                    items = [item.strip() for item in items_str.split(',')]
                    
                    # Remove @ prefix if present
                    if package.startswith('@'):
                        package = package[1:]
                    blueprint_refs.append(BlueprintReference(module_path=package, items=items))
                else:
                    # Just a blueprint module name
                    module = dep[1:] if dep.startswith('@') else dep
                    blueprint_refs.append(BlueprintReference(module_path=module))
        
        return blueprint_refs
    
    def _parse_component(self, lines: List[str], start_idx: int) -> Optional[Component]:
        """Parse a component starting at the given line."""
        line = lines[start_idx].strip()
        
        # Check for type alias (TypeName = Type or explicit type alias)
        # Skip lines with ':' in left-hand side as they should be handled by constant regex
        if '=' in line and not line.startswith('-'):
            parts = line.split('=', 1)
            if len(parts) == 2:
                name = parts[0].strip()
                value = parts[1].strip()
                # Skip if left-hand side contains ':' (let constant regex handle it)
                if ':' not in name:
                    # Only treat as type alias if name is PascalCase or contains "type" keyword
                    if (name[0].isupper() and any(c.islower() for c in name)) or 'type' in name.lower():
                        return Component(type="type_alias", name=name, value=value)
                    # Otherwise treat as constant if it looks like one
                    elif name.isupper() and '_' in name:
                        return Component(
                            type="constant",
                            name=name,
                            properties={"type": "auto"},
                            value=value
                        )
        
        # Check for constant (CONSTANT_NAME: type = value)
        if re.match(r'^[A-Z][A-Z0-9_]*:', line):
            match = re.match(r'^([A-Z][A-Z0-9_]*):\s*([^=]+)(?:\s*=\s*(.+))?$', line)
            if match:
                name, type_str, value = match.groups()
                return Component(
                    type="constant",
                    name=name,
                    properties={"type": type_str.strip()},
                    value=value.strip() if value else None
                )
        
        # Check for class definition
        class_match = re.match(r'^(\w+)(?:\(([^)]+)\))?:?\s*$', line)
        if class_match and start_idx + 1 < len(lines) and lines[start_idx + 1].strip().startswith('-'):
            name, base_class = class_match.groups()
            component = Component(
                type="class",
                name=name,
                base_class=base_class
            )
            
            # Parse class members
            i = start_idx + 1
            decorators = []
            while i < len(lines) and (lines[i].strip().startswith('-') or
                                     lines[i].strip().startswith('@') or
                                     not lines[i].strip()):
                member_line = lines[i].strip()
                if member_line.startswith('-'):
                    method = self._parse_method(member_line[1:].strip())
                    if method:
                        # Apply accumulated decorators
                        method.decorators.extend(decorators)
                        component.methods.append(method)
                        decorators = []  # Reset decorators
                elif member_line.startswith('@'):
                    # Accumulate decorators
                    decorators.append(member_line)
                i += 1
            
            return component
        
        # Check for standalone function (with decorator support)
        func_match = re.match(r'^(?:async\s+)?def\s+(\w+)\((.*?)\)(?:\s*->\s*(.+?))?:?\s*$', line)
        if func_match:
            is_async = line.strip().startswith('async ')
            name, params, return_type = func_match.groups()
            
            # Check for preceding decorators
            decorators = []
            check_idx = start_idx - 1
            while check_idx >= 0 and lines[check_idx].strip().startswith('@'):
                decorators.insert(0, lines[check_idx].strip())
                check_idx -= 1
            
            # Check for docstring
            docstring = None
            if start_idx + 1 < len(lines) and lines[start_idx + 1].strip().startswith('"""'):
                docstring = lines[start_idx + 1].strip().strip('"""')
            
            method = Method(
                name=name,
                params=params,
                return_type=return_type.strip() if return_type else None,
                is_async=is_async,
                decorators=decorators
            )
            
            return Component(
                type="function",
                name=name,
                methods=[method],
                docstring=docstring
            )
        
        return None
    
    def _parse_method(self, line: str) -> Optional[Method]:
        """Parse a method signature line."""
        # Remove comments first
        comment = None
        if '#' in line:
            parts = line.split('#', 1)
            line = parts[0].strip()
            comment = parts[1].strip()
        
        # Check for property
        if ':' in line and '(' not in line:
            parts = line.split(':', 1)
            return Method(
                name=parts[0].strip(),
                params="",
                return_type=parts[1].strip(),
                comment=comment
            )
        
        # Parse method signature
        match = re.match(r'^(?:async\s+)?(\w+)\((.*?)\)(?:\s*->\s*(.+))?$', line)
        if match:
            name, params, return_type = match.groups()
            return Method(
                name=name,
                params=params,
                return_type=return_type.strip() if return_type else None,
                comment=comment,
                is_async=line.strip().startswith('async ')
            )
        
        return None
    
    def _find_component_end(self, lines: List[str], start_idx: int) -> int:
        """Find where a component definition ends."""
        i = start_idx + 1
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines and docstrings
            if not line or line.startswith('"""'):
                i += 1
                continue
                
            # Component ends when we hit a directive or what looks like a new component
            if (line.startswith('deps:') or
                line.startswith('notes:') or
                line.startswith('#')):
                return i - 1
                
            # Check if this looks like a new component (not part of current one)
            if (line and not line.startswith('-') and not line.startswith('@')):
                # Could be a new function, class, constant, or type alias
                if (re.match(r'^(?:async\s+)?def\s+\w+\(', line) or  # function
                    re.match(r'^\w+(?:\([^)]*\))?:?\s*$', line) or  # class
                    re.match(r'^[A-Z][A-Z0-9_]*:', line) or  # constant
                    ('=' in line and not line.startswith('-'))):  # type alias or assignment
                    return i - 1
            
            i += 1
        return len(lines) - 1


# Update the existing BlueprintParser to use CompactBlueprintParser
BlueprintParser = CompactBlueprintParser