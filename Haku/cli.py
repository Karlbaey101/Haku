import os
import click
from datetime import datetime
from .models import Config, Issue
from .core import HakuCore
from .github_api import GitHubAPI
from .utils import list_local_issues, extract_repo_info, sanitize_filename

class HakuContext:
    def __init__(self):
        self.config_file = ".hakuconfig"
        self.config = Config.load(self.config_file)
        self.core = HakuCore(self.config)
        
    def save_config(self):
        self.config.save(self.config_file)

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
    success, message = ctx.obj.core.initialize_repo()
    click.echo(message)

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
    try:
        issue = ctx.obj.core.create_issue(title, body, list(label), milestone)
        click.echo(f"Created issue #{issue.number}: {issue.title}")
    except Exception as e:
        click.echo(f"Error: {str(e)}")

@cli.command()
@click.argument('issue_number', type=int)
@pass_context
def delete(ctx, issue_number):
    """Delete an issue locally"""
    success, message = ctx.obj.core.delete_issue(issue_number)
    click.echo(message)

@cli.command()
@pass_context
def push(ctx):
    """Push local issues to GitHub"""
    if not ctx.obj.config.repo_url or not ctx.obj.config.token:
        click.echo("Repository not linked or token not set. Use 'haku link' and 'haku token' first.")
        return
    
    try:
        github_api = GitHubAPI(ctx.obj.config)
        issues = ctx.obj.core.list_local_issues()
        
        for issue in issues:
            try:
                # 检查 issue 是否已存在
                try:
                    remote_issue = github_api.get_issue(issue.number)
                    # 更新现有 issue
                    result = github_api.update_issue(issue)
                    action = "updated"
                except:
                    # 创建新 issue
                    result = github_api.create_issue(issue)
                    action = "created"
                
                click.echo(f"Issue #{issue.number} {action} successfully: {issue.title}")
            except Exception as e:
                click.echo(f"Failed to push issue #{issue.number}: {str(e)}")
    
    except Exception as e:
        click.echo(f"Error: {str(e)}")

@cli.command()
@pass_context
def pull(ctx):
    """Pull issues from GitHub"""
    if not ctx.obj.config.repo_url or not ctx.obj.config.token:
        click.echo("Repository not linked or token not set. Use 'haku link' and 'haku token' first.")
        return
    
    try:
        github_api = GitHubAPI(ctx.obj.config)
        issues = github_api.list_issues(state="all")
        
        # 确保 issues 目录存在
        issues_dir = ctx.obj.config.issues_dir
        if not os.path.exists(issues_dir):
            os.makedirs(issues_dir)
        
        for issue_data in issues:
            # 创建 issue 对象
            issue = Issue(
                number=issue_data['number'],
                title=issue_data['title'],
                body=issue_data['body'] or "",
                state=issue_data['state'],
                labels=[label['name'] for label in issue_data.get('labels', [])],
                milestone=issue_data.get('milestone', {}).get('title'),
                created_at=issue_data['created_at']
            )
            
            # 生成文件名
            safe_title = sanitize_filename(issue.title)
            filename = f"{issue.number}.{safe_title}.md"
            filepath = os.path.join(issues_dir, filename)
            issue.filepath = filepath
            
            # 写入文件
            with open(filepath, 'w') as f:
                f.write(issue.to_markdown())
            
            click.echo(f"Pulled issue #{issue.number}: {issue.title}")
    
    except Exception as e:
        click.echo(f"Error: {str(e)}")

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
    
    state_filter = None
    if open:
        state_filter = "open"
    elif closed:
        state_filter = "closed"
    
    if local:
        try:
            issues = ctx.obj.core.list_local_issues(state_filter, query)
            click.echo("Local Issues:")
            click.echo("------------")
            for issue in issues:
                click.echo(f"#{issue.number}: {issue.title} [{issue.state}]")
        except Exception as e:
            click.echo(f"Error listing local issues: {str(e)}")
    
    if remote:
        if not ctx.obj.config.repo_url or not ctx.obj.config.token:
            click.echo("Repository not linked or token not set. Use 'haku link' and 'haku token' first.")
            return
        
        try:
            github_api = GitHubAPI(ctx.obj.config)
            state = "all"
            if open:
                state = "open"
            elif closed:
                state = "closed"
            
            issues = github_api.list_issues(state=state, query=query)
            click.echo("\nRemote Issues:")
            click.echo("-------------")
            for issue in issues:
                click.echo(f"#{issue['number']}: {issue['title']} [{issue['state']}]")
        except Exception as e:
            click.echo(f"Error listing remote issues: {str(e)}")

if __name__ == '__main__':
    cli()