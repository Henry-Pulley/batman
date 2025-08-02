"""Configuration file manager for safely updating config.py"""

import os
import re
from typing import List, Tuple
from pathlib import Path


class ConfigManager:
    def __init__(self, config_path: str = None):
        if config_path is None:
            # Default to src/config.py relative to this file
            self.config_path = Path(__file__).parent / "config.py"
        else:
            self.config_path = Path(config_path)
    
    def get_hate_terms(self) -> List[str]:
        """Read current hate terms from config.py"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the hate_terms list in the file
        pattern = r'hate_terms:\s*List\[str\]\s*=\s*\[(.*?)\]'
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            raise ValueError("Could not find hate_terms list in config.py")
        
        terms_str = match.group(1)
        # Extract individual terms
        terms = re.findall(r'"([^"]+)"', terms_str)
        
        return terms
    
    def add_hate_term(self, term: str) -> Tuple[bool, str]:
        """Add a new hate term to config.py"""
        # Validate input
        if not term or not term.strip():
            return False, "Term cannot be empty"
        
        term = term.strip().lower()
        
        # Check if term already exists
        current_terms = self.get_hate_terms()
        if term in [t.lower() for t in current_terms]:
            return False, "Term already exists"
        
        # Read the file
        with open(self.config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the hate_terms list
        pattern = r'(hate_terms:\s*List\[str\]\s*=\s*\[)(.*?)(\])'
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            return False, "Could not find hate_terms list in config.py"
        
        # Insert the new term
        prefix = match.group(1)
        terms_content = match.group(2)
        suffix = match.group(3)
        
        # Add the new term maintaining the format
        if terms_content.strip():
            # Add comma and newline if there are existing terms
            new_terms_content = terms_content.rstrip() + f', "{term}"'
        else:
            # First term
            new_terms_content = f'\n        "{term}"\n    '
        
        # Replace in content
        new_content = content[:match.start()] + prefix + new_terms_content + suffix + content[match.end():]
        
        # Write back to file
        with open(self.config_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        return True, "Term added successfully"
    
    def remove_hate_term(self, term: str) -> Tuple[bool, str]:
        """Remove a hate term from config.py"""
        term = term.strip().lower()
        
        # Check if term exists
        current_terms = self.get_hate_terms()
        matching_term = None
        for t in current_terms:
            if t.lower() == term:
                matching_term = t
                break
        
        if not matching_term:
            return False, "Term not found"
        
        # Read the file
        with open(self.config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find and remove the term
        # Match the term with optional comma and whitespace
        patterns = [
            f', "{matching_term}"',  # Term in middle or end with comma before
            f'"{matching_term}",',   # Term at beginning or middle with comma after
            f'"{matching_term}"'     # Term alone
        ]
        
        for pattern in patterns:
            if pattern in content:
                content = content.replace(pattern, '', 1)
                break
        
        # Clean up any double commas or extra whitespace
        content = re.sub(r',\s*,', ',', content)
        content = re.sub(r'\[\s*,', '[', content)
        content = re.sub(r',\s*\]', ']', content)
        
        # Write back to file
        with open(self.config_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return True, "Term removed successfully"
    
    def update_hate_terms(self, terms: List[str]) -> Tuple[bool, str]:
        """Replace entire hate terms list"""
        # Validate input
        if not isinstance(terms, list):
            return False, "Terms must be a list"
        
        # Remove duplicates and empty strings
        terms = list(set(term.strip() for term in terms if term.strip()))
        
        # Read the file
        with open(self.config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the hate_terms list
        pattern = r'(hate_terms:\s*List\[str\]\s*=\s*\[)(.*?)(\])'
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            return False, "Could not find hate_terms list in config.py"
        
        # Format the new terms list
        if terms:
            formatted_terms = ',\n        '.join(f'"{term}"' for term in sorted(terms))
            new_terms_content = f'\n        {formatted_terms}\n    '
        else:
            new_terms_content = ''
        
        # Replace in content
        prefix = match.group(1)
        suffix = match.group(3)
        new_content = content[:match.start()] + prefix + new_terms_content + suffix + content[match.end():]
        
        # Write back to file
        with open(self.config_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        return True, "Terms updated successfully"