import os
import re
from datetime import datetime
from typing import List, Optional
from .models import Issue

def sanitize_filename(title: str) -> str:
    """Create safe file name"""
    # Replace special char with '_'
    safe_title = re.sub(r'[^\w\s-]', '_', title)
    # Replace ' ' with '-'
    safe_title = re.sub(r'\s+', '-', safe_title)
    # Remove continuous '_'
    safe_title = re.sub(r'_{2,}', '_', safe_title)
    # Remove '-' and '_' at head and tail
    safe_title = safe_title.strip('-_')
    return safe_title

def find_issue_by_number(issues_dir: str, number: int) -> Optional[str]:
    """Find issue according to number"""
    for filename in os.listdir(issues_dir):
        if not filename.endswith('.md'):
            continue
        
        parts = filename.split('.')
        if len(parts) < 3:
            continue
        
        try:
            issue_num = int(parts[0])
        except ValueError:
            continue
        
        if issue_num == number:
            return os.path.join(issues_dir, filename)
    
    return None

def list_local_issues(issues_dir: str, 
                      state_filter: Optional[str] = None,
                      query: Optional[str] = None) -> List[Issue]:
    """List local issue"""
    if not os.path.exists(issues_dir):
        return []
    
    issues = []
    for filename in os.listdir(issues_dir):
        if not filename.endswith('.md'):
            continue
        
        filepath = os.path.join(issues_dir, filename)
        issue = Issue.from_markdown(filepath)
        if issue is None:
            continue
        
        # Apply filter
        if state_filter and issue.state != state_filter:
            continue
        if query and query.lower() not in issue.title.lower() and query.lower() not in issue.body.lower():
            continue
        
        issues.append(issue)
    
    return issues

def get_next_issue_number(issues_dir: str) -> int:
    """Get next available issue number"""
    if not os.path.exists(issues_dir):
        return 1
    
    max_num = 0
    for filename in os.listdir(issues_dir):
        if not filename.endswith('.md'):
            continue
        
        parts = filename.split('.')
        if len(parts) < 2:
            continue
        
        try:
            num = int(parts[0])
            if num > max_num:
                max_num = num
        except ValueError:
            continue
    
    return max_num + 1

def extract_repo_info(repo_url: str) -> tuple:
    repo_url = repo_url.strip('/')
    
    if repo_url.startswith("https://github.com/"):
        parts = repo_url.split('/')
        if len(parts) < 5:
            return None, None
        return parts[-2], parts[-1]
    elif repo_url.startswith("git@github.com:"):
        # git@github.com:owner/repo.git
        repo_url = repo_url.replace("git@github.com:", "")
        repo_url = repo_url.replace(".git", "")
        parts = repo_url.split('/')
        if len(parts) < 2:
            return None, None
        return parts[0], parts[1]
    else:
        parts = repo_url.split('/')
        if len(parts) >= 2:
            return parts[-2], parts[-1]
    
    return None, None