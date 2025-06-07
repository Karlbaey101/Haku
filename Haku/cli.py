import click
import os
from datetime import datetime
import requests
import json
from dataclasses import dataclass

@dataclass
class Config:
    repo_url: str = ""
    token: str = ""
    issues_dir: str = "issues"

class HakuContext:
    def __init__(self):
        self.config_file = ".hakuconfig"
        self.config = self._load_config()
        
    def _load_config(self) -> Config:
        if not os.path.exists(self.config_file):
            return Config()
        
        with open(self.config_file, 'r') as f:
            data = json.load(f)
            return Config(**data)
    
    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config.__dict__, f)

pass_context = click.make_pass_decorator(HakuContext)

@click.group()
@click.pass_context
def cli(ctx):
    """Haku - Markdown Issue Manager"""
    ctx.obj = HakuContext()

@cli.command()
@pass_context
def init(ctx):
    """Initialize a new Haku repository"""
    if os.path.exists(ctx.obj.config.issues_dir):
        click.echo("Haku repository already initialized")
        return
    
    os.makedirs(ctx.obj.config.issues_dir)
    ctx.obj.save_config()
    click.echo(f"Initialized empty Haku repository in {os.getcwd()}")

@cli.command()
@click.argument('url')
@pass_context
def link(ctx, url):
    """Link to a remote GitHub repository"""
    ctx.obj.config.repo_url = url
    ctx.obj.save_config()
    click.echo(f"Linked to remote repository: {url}")

@cli.command()
@click.argument('token')
@pass_context
def token(ctx, token):
    """Set GitHub API token"""
    ctx.obj.config.token = token
    ctx.obj.save_config()
    click.echo("GitHub token set successfully")

@cli.command()
@click.option('-t', '--title', prompt='Issue title', help='Title of the issue')
@click.option('-b', '--body', prompt='Issue description', help='Description of the issue')
@click.option('-l', '--label', multiple=True, help='Labels for the issue')
@click.option('-m', '--milestone', help='Milestone for the issue')
@pass_context
def create(ctx, title, body, label, milestone):
    """Create a new issue"""
    issues_dir = ctx.obj.config.issues_dir
    if not os.path.exists(issues_dir):
        click.echo("Haku repository not initialized. Run 'haku init' first.")
        return
    
    # Find the next issue number
    existing_issues = [f for f in os.listdir(issues_dir) if f.endswith('.md')]
    next_num = 1
    if existing_issues:
        nums = [int(f.split('.')[0]) for f in existing_issues]
        next_num = max(nums) + 1
    
    # Create filename
    safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in title)
    filename = f"{next_num}.{safe_title}.md"
    filepath = os.path.join(issues_dir, filename)
    
    # Create markdown content
    content = f"""# {title}

**Created**: {datetime.now().isoformat()}

## Description

{body}

"""
    if label:
        content += f"\n## Labels\n{', '.join(label)}\n"
    if milestone:
        content += f"\n## Milestone\n{milestone}\n"
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    click.echo(f"Created issue #{next_num}: {filepath}")

@cli.command()
@click.argument('issue_number', type=int)
@pass_context
def delete(ctx, issue_number):
    """Delete an issue locally"""
    issues_dir = ctx.obj.config.issues_dir
    if not os.path.exists(issues_dir):
        click.echo("Haku repository not initialized. Run 'haku init' first.")
        return
    
    # Find the issue file
    matching_files = [f for f in os.listdir(issues_dir) 
                     if f.startswith(f"{issue_number}.") and f.endswith('.md')]
    
    if not matching_files:
        click.echo(f"No issue found with number {issue_number}")
        return
    
    filepath = os.path.join(issues_dir, matching_files[0])
    os.remove(filepath)
    click.echo(f"Deleted issue #{issue_number}")

@cli.command()
@pass_context
def push(ctx):
    """Push local issues to GitHub"""
    if not ctx.obj.config.repo_url or not ctx.obj.config.token:
        click.echo("Repository not linked or token not set. Use 'haku link' and 'haku token' first.")
        return
    
    # Extract owner and repo from URL
    parts = ctx.obj.config.repo_url.strip('/').split('/')
    if len(parts) < 2:
        click.echo("Invalid repository URL format")
        return
    
    owner, repo = parts[-2], parts[-1]
    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = {
        "Authorization": f"token {ctx.obj.config.token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    issues_dir = ctx.obj.config.issues_dir
    if not os.path.exists(issues_dir):
        click.echo("No issues directory found")
        return
    
    for filename in os.listdir(issues_dir):
        if not filename.endswith('.md'):
            continue
        
        issue_num = filename.split('.')[0]
        filepath = os.path.join(issues_dir, filename)
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Parse content
        lines = content.split('\n')
        title = lines[0][2:].strip()  # Remove '# '
        body = '\n'.join(lines[3:]).strip()  # Skip header lines
        
        # Check if issue already exists
        exists = False
        if issue_num.isdigit():
            response = requests.get(f"{api_url}/{issue_num}", headers=headers)
            exists = response.status_code == 200
        
        if exists:
            # Update existing issue
            response = requests.patch(
                f"{api_url}/{issue_num}",
                headers=headers,
                json={"title": title, "body": body}
            )
            action = "updated"
        else:
            # Create new issue
            response = requests.post(
                api_url,
                headers=headers,
                json={"title": title, "body": body}
            )
            action = "created"
        
        if response.status_code in (200, 201):
            click.echo(f"Issue {action} successfully: {title}")
        else:
            click.echo(f"Failed to push issue: {response.json().get('message', 'Unknown error')}")

@cli.command()
@pass_context
def pull(ctx):
    """Pull issues from GitHub"""
    if not ctx.obj.config.repo_url or not ctx.obj.config.token:
        click.echo("Repository not linked or token not set. Use 'haku link' and 'haku token' first.")
        return
    
    # Extract owner and repo from URL
    parts = ctx.obj.config.repo_url.strip('/').split('/')
    if len(parts) < 2:
        click.echo("Invalid repository URL format")
        return
    
    owner, repo = parts[-2], parts[-1]
    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = {
        "Authorization": f"token {ctx.obj.config.token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Create issues directory if it doesn't exist
    issues_dir = ctx.obj.config.issues_dir
    if not os.path.exists(issues_dir):
        os.makedirs(issues_dir)
    
    # Get all issues from GitHub
    response = requests.get(api_url, headers=headers)
    if response.status_code != 200:
        click.echo(f"Failed to fetch issues: {response.json().get('message', 'Unknown error')}")
        return
    
    issues = response.json()
    for issue in issues:
        filename = f"{issue['number']}.{issue['title']}.md"
        safe_filename = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in filename)
        filepath = os.path.join(issues_dir, safe_filename)
        
        # Prepare content
        content = f"""# {issue['title']}

**Created**: {issue['created_at']}
**State**: {'open' if issue['state'] == 'open' else 'closed'}

## Description

{issue['body']}

"""
        if issue.get('labels'):
            content += f"\n## Labels\n{', '.join(label['name'] for label in issue['labels'])}\n"
        if issue.get('milestone'):
            content += f"\n## Milestone\n{issue['milestone']['title']}\n"
        
        with open(filepath, 'w') as f:
            f.write(content)
        
        click.echo(f"Pulled issue #{issue['number']}: {issue['title']}")

@cli.command()
@click.option('-r', '--remote', is_flag=True, help='List remote issues')
@click.option('-l', '--local', is_flag=True, help='List local issues')
@click.option('-o', '--open', is_flag=True, help='Filter open issues')
@click.option('-c', '--closed', is_flag=True, help='Filter closed issues')
@click.option('-q', '--query', help='Search query')
@pass_context
def list(ctx, remote, local, open, closed, query):
    """List issues"""
    if not remote and not local:
        local = True  # Default to local
    
    if local:
        issues_dir = ctx.obj.config.issues_dir
        if not os.path.exists(issues_dir):
            click.echo("No issues directory found")
            return
        
        click.echo("Local Issues:")
        click.echo("------------")
        for filename in sorted(os.listdir(issues_dir)):
            if not filename.endswith('.md'):
                continue
            
            parts = filename.split('.')
            if len(parts) < 3:
                continue
            
            issue_num = parts[0]
            title = '.'.join(parts[1:-1])  # Handle titles with dots
            
            # Read state from file
            filepath = os.path.join(issues_dir, filename)
            with open(filepath, 'r') as f:
                lines = f.readlines()
                state = "unknown"
                for line in lines:
                    if line.startswith("**State**: "):
                        state = line.split(": ")[1].strip()
                        break
            
            # Apply filters
            if open and state != 'open':
                continue
            if closed and state != 'closed':
                continue
            if query and query.lower() not in title.lower():
                continue
            
            click.echo(f"#{issue_num}: {title} [{state}]")
    
    if remote:
        if not ctx.obj.config.repo_url or not ctx.obj.config.token:
            click.echo("Repository not linked or token not set. Use 'haku link' and 'haku token' first.")
            return
        
        # Extract owner and repo from URL
        parts = ctx.obj.config.repo_url.strip('/').split('/')
        if len(parts) < 2:
            click.echo("Invalid repository URL format")
            return
        
        owner, repo = parts[-2], parts[-1]
        api_url = f"https://api.github.com/repos/{owner}/{repo}/issues"
        headers = {
            "Authorization": f"token {ctx.obj.config.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        params = {}
        if open:
            params['state'] = 'open'
        if closed:
            params['state'] = 'closed'
        if query:
            params['q'] = f'repo:{owner}/{repo} {query} in:title,body'
        
        response = requests.get(api_url, headers=headers, params=params)
        if response.status_code != 200:
            click.echo(f"Failed to fetch issues: {response.json().get('message', 'Unknown error')}")
            return
        
        issues = response.json()
        click.echo("\nRemote Issues:")
        click.echo("-------------")
        for issue in issues:
            click.echo(f"#{issue['number']}: {issue['title']} [{issue['state']}]")

if __name__ == '__main__':
    cli()