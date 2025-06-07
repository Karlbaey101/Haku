import os
import json
import click
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# 配置文件路径
CONFIG_FILE = ".hakuconfig"
ISSUES_DIR = "issues"

# GitHub API设置
GITHUB_API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github.v3+json"}

class HakuConfig:
    def __init__(self, path):
        self.path = path
        self.config = {
            "repo_url": "",
            "token": "",
            "last_sync": "",
            "pending_deletes": []
        }
        
    def load(self):
        if self.path.exists():
            with open(self.path, "r") as f:
                self.config = json.load(f)
        return self.config
    
    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.config, f, indent=2)

def get_config(ctx):
    config_path = Path(ctx.obj["root"]) / CONFIG_FILE
    config = HakuConfig(config_path)
    return config.load()

def save_config(ctx, data):
    config_path = Path(ctx.obj["root"]) / CONFIG_FILE
    config = HakuConfig(config_path)
    config.config = data
    config.save()

def validate_config(config):
    if not config.get("repo_url") or not config.get("token"):
        raise click.ClickException("Repository not linked or token missing. Use 'haku link' and 'haku token'")

def github_request(method, url, token, data=None, params=None):
    headers = {**HEADERS, "Authorization": f"token {token}"}
    try:
        response = requests.request(method, url, json=data, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        # 处理速率限制
        if "X-RateLimit-Remaining" in response.headers:
            remaining = int(response.headers["X-RateLimit-Remaining"])
            if remaining < 5:
                reset_time = datetime.fromtimestamp(int(response.headers["X-RateLimit-Reset"]))
                raise click.ClickException(f"GitHub API rate limit low. Resets at: {reset_time}")
        
        return response
    except requests.exceptions.RequestException as e:
        raise click.ClickException(f"API request failed: {str(e)}")

def parse_repo_url(repo_url):
    """将仓库URL转换为owner/repo格式"""
    if repo_url.startswith(("http://", "https://")):
        path = urlparse(repo_url).path.lstrip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return path
    return repo_url

def create_issue_file(ctx, title, labels, milestone, body=""):
    issues_dir = Path(ctx.obj["root"]) / ISSUES_DIR
    issues_dir.mkdir(exist_ok=True)
    
    # 生成文件名（用下划线替换空格）
    filename = f"0.{title.replace(' ', '_')}.md"
    filepath = issues_dir / filename
    
    # 写入元数据和内容
    content = f"---\nid: 0\ntitle: {title}\n"
    if labels:
        content += f"labels: {','.join(labels)}\n"
    if milestone:
        content += f"milestone: {milestone}\n"
    content += f"state: open\ncreated: {datetime.now().isoformat()}\n---\n\n{body}"
    
    with open(filepath, "w") as f:
        f.write(content)
    
    return filepath

def parse_issue_metadata(filepath):
    """从Markdown文件中解析元数据"""
    with open(filepath, "r") as f:
        lines = f.readlines()
    
    if not lines or not lines[0].startswith("---"):
        return None
    
    metadata = {}
    in_metadata = False
    for line in lines:
        if line.startswith("---"):
            if in_metadata:
                break
            in_metadata = True
            continue
        if in_metadata and ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    
    return metadata

def backup_issues(ctx):
    """创建issues目录的备份"""
    issues_dir = Path(ctx.obj["root"]) / ISSUES_DIR
    if not issues_dir.exists():
        return
    
    backup_dir = Path(ctx.obj["root"]) / f"issues_backup_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    os.rename(issues_dir, backup_dir)
    click.echo(f"Created backup at: {backup_dir}")

# CLI命令
@click.group()
@click.pass_context
def cli(ctx):
    """Haku - GitHub Issue Management Tool"""
    ctx.ensure_object(dict)
    ctx.obj["root"] = os.getcwd()

@cli.command()
@click.pass_context
def init(ctx):
    """Initialize Haku repository"""
    root = Path(ctx.obj["root"])
    issues_dir = root / ISSUES_DIR
    config_file = root / CONFIG_FILE
    
    if config_file.exists():
        raise click.ClickException("Haku repository already initialized")
    
    issues_dir.mkdir(exist_ok=True)
    save_config(ctx, {
        "repo_url": "",
        "token": "",
        "last_sync": "",
        "pending_deletes": []
    })
    
    click.echo(f"Haku repository initialized at: {root}")
    click.echo(f"Issues directory: {issues_dir}")

@cli.command()
@click.argument("repo_url")
@click.pass_context
def link(ctx, repo_url):
    """Link remote GitHub repository"""
    repo_path = parse_repo_url(repo_url)
    config = get_config(ctx)
    config["repo_url"] = repo_path
    save_config(ctx, config)
    click.echo(f"Linked repository: {repo_path}")

@cli.command()
@click.argument("token")
@click.pass_context
def token(ctx, token):
    """Set GitHub access token"""
    config = get_config(ctx)
    config["token"] = token
    save_config(ctx, config)
    click.echo("GitHub token set")

@cli.command()
@click.option("-t", "--title", prompt="Issue title", help="Title of the issue")
@click.option("-b", "--body", prompt="Issue description", help="Description of the issue")
@click.option("-l", "--label", multiple=True, help="Labels for the issue")
@click.option("-m", "--milestone", help="Milestone for the issue")
@click.pass_context
def create(ctx, title, body, label, milestone):
    """Create a new issue"""
    config = get_config(ctx)
    if not config["repo_url"]:
        raise click.ClickException("Repository not linked. Use 'haku link'")
    
    filepath = create_issue_file(ctx, title, label, milestone, body)
    click.echo(f"Created issue draft at: {filepath}")
    click.echo("Edit the file and use 'haku push' to publish")

@cli.command()
@click.argument("issue_id", type=int)
@click.pass_context
def delete(ctx, issue_id):
    """Delete an issue locally and mark for remote deletion"""
    config = get_config(ctx)
    issues_dir = Path(ctx.obj["root"]) / ISSUES_DIR
    
    # 查找匹配的文件
    found = False
    for file in issues_dir.glob(f"{issue_id}.*.md"):
        os.remove(file)
        found = True
        click.echo(f"Deleted local issue: {file.name}")
    
    if not found:
        raise click.ClickException(f"No local issue found with ID: {issue_id}")
    
    # 添加到待删除列表
    if issue_id not in config["pending_deletes"]:
        config["pending_deletes"].append(issue_id)
        save_config(ctx, config)
        click.echo(f"Issue {issue_id} marked for remote deletion")

@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be pushed")
@click.pass_context
def push(ctx, dry_run):
    """Push local changes to GitHub"""
    config = get_config(ctx)
    validate_config(config)
    repo = config["repo_url"]
    token = config["token"]
    issues_dir = Path(ctx.obj["root"]) / ISSUES_DIR
    
    # 处理待删除的issue
    if not dry_run and config["pending_deletes"]:
        for issue_id in config["pending_deletes"][:]:
            url = f"{GITHUB_API}/repos/{repo}/issues/{issue_id}"
            if dry_run:
                click.echo(f"[Dry Run] Would close issue #{issue_id}")
            else:
                try:
                    github_request("PATCH", url, token, {"state": "closed"})
                    config["pending_deletes"].remove(issue_id)
                    click.echo(f"Closed issue #{issue_id}")
                except click.ClickException as e:
                    click.echo(f"Error closing issue #{issue_id}: {str(e)}")
        save_config(ctx, config)
    
    # 处理新建/更新的issue
    for file in issues_dir.glob("*.md"):
        meta = parse_issue_metadata(file)
        if not meta:
            click.echo(f"Skipping invalid issue file: {file.name}")
            continue
        
        issue_data = {
            "title": meta.get("title", "Untitled"),
            "body": "\n".join(open(file).readlines()[meta.get("body_start", 0):]),
            "labels": meta.get("labels", "").split(",") if meta.get("labels") else [],
        }
        
        if meta.get("milestone"):
            issue_data["milestone"] = meta.get("milestone")
        
        issue_id = meta.get("id", 0)
        if issue_id == 0:  # 新建issue
            if dry_run:
                click.echo(f"[Dry Run] Would create issue: {issue_data['title']}")
            else:
                try:
                    url = f"{GITHUB_API}/repos/{repo}/issues"
                    response = github_request("POST", url, token, issue_data).json()
                    new_id = response["number"]
                    
                    # 更新本地文件
                    new_name = f"{new_id}.{file.stem.split('.', 1)[1]}.md"
                    new_path = file.parent / new_name
                    os.rename(file, new_path)
                    
                    # 更新元数据
                    with open(new_path, "r+") as f:
                        content = f.read().replace("id: 0", f"id: {new_id}", 1)
                        f.seek(0)
                        f.write(content)
                        f.truncate()
                    
                    click.echo(f"Created issue #{new_id}: {issue_data['title']}")
                except Exception as e:
                    click.echo(f"Error creating issue: {str(e)}")
        else:  # 更新issue
            if dry_run:
                click.echo(f"[Dry Run] Would update issue #{issue_id}: {issue_data['title']}")
            else:
                try:
                    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_id}"
                    github_request("PATCH", url, token, issue_data)
                    click.echo(f"Updated issue #{issue_id}")
                except Exception as e:
                    click.echo(f"Error updating issue #{issue_id}: {str(e)}")
    
    if not dry_run:
        config["last_sync"] = datetime.now().isoformat()
        save_config(ctx, config)

@cli.command()
@click.option("--force", is_flag=True, help="Overwrite local changes")
@click.pass_context
def pull(ctx, force):
    """Pull issues from GitHub"""
    config = get_config(ctx)
    validate_config(config)
    repo = config["repo_url"]
    token = config["token"]
    issues_dir = Path(ctx.obj["root"]) / ISSUES_DIR
    
    if not force:
        # 检查本地是否有未推送的修改
        for file in issues_dir.glob("*.md"):
            meta = parse_issue_metadata(file)
            if meta and meta.get("id", 0) == 0:
                raise click.ClickException("Local changes detected. Use --force to overwrite or push first")
    
    # 创建备份
    backup_issues(ctx)
    issues_dir.mkdir(exist_ok=True)
    
    # 获取所有issue
    page = 1
    while True:
        url = f"{GITHUB_API}/repos/{repo}/issues"
        params = {"state": "all", "per_page": 100, "page": page}
        try:
            response = github_request("GET", url, token, params=params).json()
            if not response:
                break
                
            for issue in response:
                if "pull_request" in issue:  # 跳过PR
                    continue
                
                filename = f"{issue['number']}.{issue['title'].replace(' ', '_')}.md"
                filepath = issues_dir / filename
                
                # 构建文件内容
                content = f"---\n"
                content += f"id: {issue['number']}\n"
                content += f"title: {issue['title']}\n"
                if issue.get("labels"):
                    content += f"labels: {','.join([l['name'] for l in issue['labels']])}\n"
                if issue.get("milestone"):
                    content += f"milestone: {issue['milestone']['number']}\n"
                content += f"state: {issue['state']}\n"
                content += f"created: {issue['created_at']}\n"
                content += f"updated: {issue['updated_at']}\n---\n\n"
                content += issue["body"] or ""
                
                with open(filepath, "w") as f:
                    f.write(content)
            
            page += 1
        except Exception as e:
            click.echo(f"Error pulling issues: {str(e)}")
            break
    
    config["last_sync"] = datetime.now().isoformat()
    save_config(ctx, config)
    click.echo(f"Pulled issues to: {issues_dir}")

@cli.command()
@click.option("-l", "--local", "source", flag_value="local", default=True, help="List local issues")
@click.option("-r", "--remote", "source", flag_value="remote", help="List remote issues")
@click.option("-o", "--open", "state", flag_value="open", help="Show only open issues")
@click.option("-c", "--closed", "state", flag_value="closed", help="Show only closed issues")
@click.option("-q", "--query", help="Search query")
@click.pass_context
def list(ctx, source, state, query):
    """List issues"""
    if source == "remote":
        config = get_config(ctx)
        validate_config(config)
        repo = config["repo_url"]
        token = config["token"]
        
        params = {"per_page": 100}
        if state:
            params["state"] = state
        if query:
            params["q"] = f"repo:{repo} {query}"
        
        try:
            url = f"{GITHUB_API}/search/issues"
            response = github_request("GET", url, token, params=params).json()
            
            click.echo("Remote Issues:")
            for item in response.get("items", []):
                if "pull_request" in item:
                    continue
                click.echo(f"#{item['number']} [{item['state']}] {item['title']}")
        except Exception as e:
            click.echo(f"Error listing remote issues: {str(e)}")
    else:
        issues_dir = Path(ctx.obj["root"]) / ISSUES_DIR
        click.echo("Local Issues:")
        
        for file in issues_dir.glob("*.md"):
            meta = parse_issue_metadata(file)
            if not meta:
                continue
                
            if state and meta.get("state") != state:
                continue
                
            if query and query.lower() not in (meta.get("title") or "").lower():
                continue
                
            click.echo(f"#{meta.get('id')} [{meta.get('state')}] {meta.get('title')}")

if __name__ == "__main__":
    cli(obj={})