#!/usr/bin/env python3
import os
import json
import click
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Constants
CONFIG_FILE = ".hakuconfig"
ISSUES_DIR = "issues"
GITHUB_API = "https://api.github.com"
BACKUP_DIR = ".hakubackups"

class HakuConfig:
    def __init__(self):
        self.repo_url = None
        self.token = None
        self.initialized = False
        self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                self.repo_url = config.get('repo_url')
                self.token = config.get('token')
                self.initialized = True

    def save_config(self):
        config = {
            'repo_url': self.repo_url,
            'token': self.token
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
        self.initialized = True

    def validate(self):
        if not self.initialized:
            raise click.UsageError("Repository not initialized. Run 'haku init' first.")
        if not self.repo_url:
            raise click.UsageError("Repository not linked. Run 'haku link' first.")
        if not self.token:
            raise click.UsageError("GitHub token not set. Run 'haku token' first.")

config = HakuConfig()

def get_repo_owner_and_name(repo_url: str) -> tuple:
    """Extract owner and repo name from GitHub URL"""
    parts = repo_url.rstrip('/').split('/')
    if len(parts) < 2:
        raise click.BadParameter("Invalid GitHub repository URL")
    return parts[-2], parts[-1]

def create_backup():
    """Create backup of issues before destructive operations"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}")
    os.makedirs(backup_path)
    
    if os.path.exists(ISSUES_DIR):
        for filename in os.listdir(ISSUES_DIR):
            src = os.path.join(ISSUES_DIR, filename)
            dst = os.path.join(backup_path, filename)
            with open(src, 'r') as f_src, open(dst, 'w') as f_dst:
                f_dst.write(f_src.read())

def validate_markdown_file(filepath: str) -> bool:
    """Basic validation of Markdown file"""
    if not os.path.exists(filepath):
        return False
    
    with open(filepath, 'r') as f:
        content = f.read()
        return len(content.strip()) > 0

def handle_github_error(response):
    """Handle GitHub API errors"""
    if response.status_code == 401:
        raise click.ClickException("Authentication failed. Check your token.")
    elif response.status_code == 403:
        if 'X-RateLimit-Remaining' in response.headers and response.headers['X-RateLimit-Remaining'] == '0':
            reset_time = datetime.fromtimestamp(int(response.headers['X-RateLimit-Reset']))
            raise click.ClickException(f"Rate limit exceeded. Try again after {reset_time}")
        raise click.ClickException("Forbidden. You may not have permission for this action.")
    elif response.status_code == 404:
        raise click.ClickException("Repository not found. Check the URL.")
    elif response.status_code >= 400:
        try:
            error_msg = response.json().get('message', 'Unknown error')
            raise click.ClickException(f"GitHub API error: {error_msg}")
        except ValueError:
            raise click.ClickException(f"GitHub API error: {response.text}")

def get_issue_filename(issue_number: int, title: str) -> str:
    """Generate filename for an issue"""
    # Remove special characters from title for filename safety
    safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in title)
    safe_title = safe_title.replace(' ', '_').lower()
    return f"{issue_number}.{safe_title}.md"

def parse_issue_filename(filename: str) -> tuple:
    """Extract issue number and title from filename"""
    parts = filename.split('.')
    if len(parts) < 3:
        return None, None
    try:
        issue_number = int(parts[0])
    except ValueError:
        return None, None
    title = '.'.join(parts[1:-1])  # Handle titles with dots
    return issue_number, title

@click.group()
def cli():
    """Haku - A command-line tool for managing GitHub issues as Markdown files"""
    pass

@cli.command()
def init():
    """Initialize the current directory as a Haku repository"""
    if config.initialized:
        click.confirm("This directory is already initialized. Reinitialize?", abort=True)
    
    if not os.path.exists(ISSUES_DIR):
        os.makedirs(ISSUES_DIR)
        click.echo(f"Created {ISSUES_DIR} directory")
    
    config.save_config()
    click.echo("Haku repository initialized")

@cli.command()
@click.argument('repo_url')
def link(repo_url: str):
    """Link to a remote GitHub repository"""
    if not repo_url.startswith(('http://', 'https://')):
        repo_url = f"https://github.com/{repo_url}"
    
    # Validate the repo exists
    try:
        owner, repo = get_repo_owner_and_name(repo_url)
        test_url = f"{GITHUB_API}/repos/{owner}/{repo}"
        response = requests.get(test_url)
        if response.status_code != 200:
            handle_github_error(response)
    except Exception as e:
        raise click.ClickException(f"Failed to validate repository: {str(e)}")
    
    config.repo_url = repo_url
    config.save_config()
    click.echo(f"Linked to repository: {repo_url}")

@cli.command()
@click.argument('token')
def token(token: str):
    """Set GitHub personal access token"""
    config.token = token
    config.save_config()
    click.echo("GitHub token set")

@cli.command()
@click.option('-t', '--title', prompt='Issue title', help='Title of the issue')
@click.option('-b', '--body', prompt='Issue description', help='Description of the issue')
@click.option('-l', '--label', multiple=True, help='Labels for the issue')
@click.option('-m', '--milestone', type=int, help='Milestone number for the issue')
@click.option('--dry-run', is_flag=True, help='Show what would be created without actually creating')
def create(title: str, body: str, label: List[str], milestone: Optional[int], dry_run: bool):
    """Create a new issue"""
    config.validate()
    
    owner, repo = get_repo_owner_and_name(config.repo_url) # type: ignore
    
    issue_data = {
        'title': title,
        'body': body,
    }
    
    if label:
        issue_data['labels'] = list(label)
    if milestone:
        issue_data['milestone'] = milestone # type: ignore
    
    if dry_run:
        click.echo("Dry run - would create issue with:")
        click.echo(json.dumps(issue_data, indent=2))
        return
    
    headers = {
        'Authorization': f"token {config.token}",
        'Accept': 'application/vnd.github.v3+json'
    }
    
    try:
        response = requests.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues",
            headers=headers,
            json=issue_data
        )
        
        if response.status_code == 201:
            issue = response.json()
            filename = get_issue_filename(issue['number'], issue['title'])
            filepath = os.path.join(ISSUES_DIR, filename)
            
            with open(filepath, 'w') as f:
                f.write(f"# {issue['title']}\n\n")
                f.write(f"{issue['body']}\n\n")
                if issue.get('labels'):
                    f.write(f"Labels: {', '.join(l['name'] for l in issue['labels'])}\n")
                if issue.get('milestone'):
                    f.write(f"Milestone: {issue['milestone']['title']}\n")
                f.write(f"State: {issue['state']}\n")
                f.write(f"Created at: {issue['created_at']}\n")
                if issue.get('closed_at'):
                    f.write(f"Closed at: {issue['closed_at']}\n")
            
            click.echo(f"Created issue #{issue['number']}: {issue['title']}")
            click.echo(f"Saved to: {filepath}")
        else:
            handle_github_error(response)
    except requests.exceptions.RequestException as e:
        raise click.ClickException(f"Failed to create issue: {str(e)}")

@cli.command()
@click.argument('issue_number', type=int)
@click.option('--dry-run', is_flag=True, help='Show what would be deleted without actually deleting')
def delete(issue_number: int, dry_run: bool):
    """Delete an issue locally"""
    config.validate()
    
    # Find the file matching the issue number
    found = False
    for filename in os.listdir(ISSUES_DIR):
        current_number, _ = parse_issue_filename(filename)
        if current_number == issue_number:
            found = True
            filepath = os.path.join(ISSUES_DIR, filename)
            
            if dry_run:
                click.echo(f"Dry run - would delete: {filepath}")
            else:
                create_backup()
                os.remove(filepath)
                click.echo(f"Deleted local issue #{issue_number}")
            break
    
    if not found:
        raise click.ClickException(f"No local issue found with number {issue_number}")

@cli.command()
@click.argument('issue_number', type=int, required=False)
@click.option('--all', is_flag=True, help='Push all local issues')
@click.option('--dry-run', is_flag=True, help='Show what would be pushed without actually pushing')
def push(issue_number: Optional[int], all: bool, dry_run: bool):
    """Push local issue(s) to GitHub"""
    config.validate()
    
    if not issue_number and not all:
        raise click.UsageError("You must specify either an issue number or --all")
    
    owner, repo = get_repo_owner_and_name(config.repo_url) # type: ignore
    headers = {
        'Authorization': f"token {config.token}",
        'Accept': 'application/vnd.github.v3+json'
    }
    
    files_to_push = []
    
    # Collect files to push
    for filename in os.listdir(ISSUES_DIR):
        current_number, title = parse_issue_filename(filename)
        if current_number is None:
            continue
            
        if all or current_number == issue_number:
            filepath = os.path.join(ISSUES_DIR, filename)
            if not validate_markdown_file(filepath):
                click.echo(f"Skipping invalid file: {filename}")
                continue
            files_to_push.append((current_number, title, filepath))
    
    if not files_to_push:
        raise click.ClickException("No valid issues found to push")
    
    for number, title, filepath in files_to_push:
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Parse content (simplistic approach)
        lines = content.split('\n')
        body = '\n'.join(lines[2:])  # Skip title line
        
        issue_data = {
            'title': title,
            'body': body
        }
        
        if dry_run:
            click.echo(f"Dry run - would push issue #{number}:")
            click.echo(json.dumps(issue_data, indent=2))
            continue
        
        try:
            if number > 0:  # Existing issue (update)
                url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{number}"
                response = requests.patch(url, headers=headers, json=issue_data)
            else:  # New issue (create)
                url = f"{GITHUB_API}/repos/{owner}/{repo}/issues"
                response = requests.post(url, headers=headers, json=issue_data)
            
            if response.status_code in (200, 201):
                issue = response.json()
                if number <= 0:  # New issue - rename file
                    old_path = filepath
                    new_filename = get_issue_filename(issue['number'], issue['title'])
                    new_path = os.path.join(ISSUES_DIR, new_filename)
                    os.rename(old_path, new_path)
                    click.echo(f"Created new issue #{issue['number']}: {issue['title']}")
                else:
                    click.echo(f"Updated issue #{issue['number']}: {issue['title']}")
            else:
                handle_github_error(response)
        except requests.exceptions.RequestException as e:
            raise click.ClickException(f"Failed to push issue #{number}: {str(e)}")

@cli.command()
@click.argument('issue_number', type=int, required=False)
@click.option('--all', is_flag=True, help='Pull all remote issues')
@click.option('--dry-run', is_flag=True, help='Show what would be pulled without actually pulling')
def pull(issue_number: Optional[int], all: bool, dry_run: bool):
    """Pull issue(s) from GitHub"""
    config.validate()
    
    if not issue_number and not all:
        raise click.UsageError("You must specify either an issue number or --all")
    
    owner, repo = get_repo_owner_and_name(config.repo_url) # type: ignore
    headers = {
        'Authorization': f"token {config.token}",
        'Accept': 'application/vnd.github.v3+json'
    }
    
    try:
        if all:
            # Get all issues (paginated)
            page = 1
            issues = []
            while True:
                url = f"{GITHUB_API}/repos/{owner}/{repo}/issues?state=all&page={page}&per_page=100"
                response = requests.get(url, headers=headers)
                if response.status_code != 200:
                    handle_github_error(response)
                
                new_issues = response.json()
                if not new_issues:
                    break
                
                issues.extend(new_issues)
                page += 1
            
            if dry_run:
                click.echo(f"Dry run - would pull {len(issues)} issues")
                return
            
            for issue in issues:
                save_issue_locally(issue)
            click.echo(f"Pulled {len(issues)} issues")
        else:
            # Get single issue
            url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                issue = response.json()
                if dry_run:
                    click.echo(f"Dry run - would pull issue #{issue['number']}: {issue['title']}")
                else:
                    save_issue_locally(issue)
                    click.echo(f"Pulled issue #{issue['number']}: {issue['title']}")
            else:
                handle_github_error(response)
    except requests.exceptions.RequestException as e:
        raise click.ClickException(f"Failed to pull issues: {str(e)}")

def save_issue_locally(issue: Dict):
    """Save an issue to local file"""
    filename = get_issue_filename(issue['number'], issue['title'])
    filepath = os.path.join(ISSUES_DIR, filename)
    
    with open(filepath, 'w') as f:
        f.write(f"# {issue['title']}\n\n")
        f.write(f"{issue['body']}\n\n")
        if issue.get('labels'):
            f.write(f"Labels: {', '.join(l['name'] for l in issue['labels'])}\n")
        if issue.get('milestone'):
            f.write(f"Milestone: {issue['milestone']['title']}\n")
        f.write(f"State: {issue['state']}\n")
        f.write(f"Created at: {issue['created_at']}\n")
        if issue.get('closed_at'):
            f.write(f"Closed at: {issue['closed_at']}\n")

@cli.command()
@click.option('-r', '--remote', is_flag=True, help='List remote issues')
@click.option('-l', '--local', is_flag=True, help='List local issues')
@click.option('-o', '--open', is_flag=True, help='Filter open issues')
@click.option('-c', '--closed', is_flag=True, help='Filter closed issues')
@click.option('-q', '--query', help='Search query for issues')
def list(remote: bool, local: bool, open: bool, closed: bool, query: Optional[str]):
    """List issues"""
    if not remote and not local:
        local = True  # Default to local
    
    if remote:
        config.validate()
        owner, repo = get_repo_owner_and_name(config.repo_url) # type: ignore
        headers = {
            'Authorization': f"token {config.token}",
            'Accept': 'application/vnd.github.v3+json'
        }
        
        params = {}
        if open and not closed:
            params['state'] = 'open'
        elif closed and not open:
            params['state'] = 'closed'
        if query:
            params['filter'] = 'all'
        
        try:
            url = f"{GITHUB_API}/repos/{owner}/{repo}/issues"
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                issues = response.json()
                click.echo("Remote issues:")
                for issue in issues:
                    if query and query.lower() not in issue['title'].lower() and query.lower() not in issue.get('body', '').lower():
                        continue
                    click.echo(f"#{issue['number']}: {issue['title']} [{issue['state']}]")
            else:
                handle_github_error(response)
        except requests.exceptions.RequestException as e:
            raise click.ClickException(f"Failed to list remote issues: {str(e)}")
    
    if local:
        if not os.path.exists(ISSUES_DIR):
            click.echo("No local issues directory found")
            return
        
        click.echo("Local issues:")
        for filename in sorted(os.listdir(ISSUES_DIR)):
            number, title = parse_issue_filename(filename)
            if number is None:
                continue
                
            # Read state from file
            filepath = os.path.join(ISSUES_DIR, filename)
            try:
                with open(filepath, 'r') as f: # type: ignore
                    content = f.read()
                    state = 'unknown'
                    for line in content.split('\n'):
                        if line.startswith('State:'):
                            state = line.split(':')[1].strip().lower()
                            break
                
                # Apply filters
                if open and state != 'open':
                    continue
                if closed and state != 'closed':
                    continue
                if query and query.lower() not in title.lower() and query.lower() not in content.lower():
                    continue
                
                click.echo(f"#{number}: {title} [{state}]")
            except IOError:
                click.echo(f"#{number}: {title} [error reading file]")

if __name__ == '__main__':
    cli()