import os
import click
from datetime import datetime
from .models import Config, Issue
from .utils import sanitize_filename, get_next_issue_number, find_issue_by_number

class HakuCore:
    def __init__(self, config: Config):
        self.config = config
    
    def initialize_repo(self):
        issues_dir = self.config.issues_dir
        if os.path.exists(issues_dir):
            return False, "Haku repository already initialized"
        
        os.makedirs(issues_dir)
        self.config.save()
        return True, f"Initialized empty Haku repository in {os.getcwd()}"
    
    def create_issue(self, title: str, body: str, labels: list, milestone: str) -> Issue:
        issues_dir = self.config.issues_dir
        if not os.path.exists(issues_dir):
            raise Exception("Haku repository not initialized. Run 'haku init' first.")
        
        next_num = get_next_issue_number(issues_dir)
        
        safe_title = sanitize_filename(title)
        filename = f"{next_num}.{safe_title}.md"
        filepath = os.path.join(issues_dir, filename)
        
        issue = Issue(
            number=next_num,
            title=title,
            body=body,
            labels=labels,
            milestone=milestone,
            created_at=datetime.now().isoformat(),
            filepath=filepath
        )
        
        with open(filepath, 'w') as f:
            f.write(issue.to_markdown())
        
        return issue
    
    def delete_issue(self, number: int) -> bool:
        issues_dir = self.config.issues_dir
        if not os.path.exists(issues_dir):
            raise Exception("Haku repository not initialized. Run 'haku init' first.")
        
        filepath = find_issue_by_number(issues_dir, number)
        if not filepath:
            return False, f"No issue found with number {number}" # type: ignore
        
        os.remove(filepath)
        return True, f"Deleted issue #{number}" # type: ignore
    
    def list_local_issues(self, state_filter: str = None, query: str = None) -> List[Issue]: # type: ignore
        from .utils import list_local_issues
        return list_local_issues(self.config.issues_dir, state_filter, query)