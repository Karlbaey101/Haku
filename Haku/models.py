from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import datetime
import os
import json

@dataclass
class Config:
    repo_url: str = ""
    token: str = ""
    issues_dir: str = "issues"
    
    @classmethod
    def load(cls, config_file: str = ".hakuconfig") -> "Config":
        """Load config from file"""
        if not os.path.exists(config_file):
            return cls()
        
        with open(config_file, 'r') as f:
            data = json.load(f)
            return cls(**data)
    
    def save(self, config_file: str = ".hakuconfig"):
        """Save config to file"""
        with open(config_file, 'w') as f:
            json.dump(self.__dict__, f)

@dataclass
class Issue:
    number: int
    title: str
    body: str
    state: str = "open"
    labels: List[str] = None # type: ignore
    milestone: Optional[str] = None
    created_at: Optional[str] = None
    filepath: Optional[str] = None
    
    @classmethod
    def from_markdown(cls, filepath: str):
        """Create issue from markdown file"""
        filename = os.path.basename(filepath)
        parts = filename.split('.')
        if len(parts) < 3:
            return None
        
        try:
            number = int(parts[0])
        except ValueError:
            return None
        
        title = '.'.join(parts[1:-1])
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        # parse markdown
        lines = content.split('\n')
        state = "open"
        created_at = ""
        body_lines = []
        labels = []
        milestone = None
        
        for line in lines:
            if line.startswith("**Created**: "):
                created_at = line.split(": ")[1].strip()
            elif line.startswith("**State**: "):
                state = line.split(": ")[1].strip()
            elif line.startswith("## Labels"):
                # Skip the title
                continue
            elif line.startswith("## Milestone"):
                # Skip the title
                continue
            elif line.strip() == "":
                continue
            else:
                body_lines.append(line)
        
        body = '\n'.join(body_lines).strip()
        
        return cls(
            number=number,
            title=title,
            body=body,
            state=state,
            labels=labels,
            milestone=milestone,
            created_at=created_at,
            filepath=filepath
        )
    
    def to_markdown(self) -> str:
        """Generate markdown file"""
        content = f"""# {self.title}

**Created**: {self.created_at or datetime.now().isoformat()}
**State**: {self.state}

## Description

{self.body}
"""
        if self.labels:
            content += f"\n## Labels\n{', '.join(self.labels)}\n"
        if self.milestone:
            content += f"\n## Milestone\n{self.milestone}\n"
        
        return content