# haku.py
import os
import json
import click
import requests
from pathlib import Path

CONFIG_FILE = '.haku_config.json'
ISSUE_FOLDER = 'issues'
GITHUB_API_URL = 'https://api.github.com'

# === 配置相关 ===
def load_config():
    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

# === GitHub 相关 ===
def github_headers(token):
    return {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github+json'
    }

@click.group()
def cli():
    """Haku - 使用 Markdown 管理 GitHub Issue 的工具"""
    pass

@cli.command()
def init():
    os.makedirs(ISSUE_FOLDER, exist_ok=True)
    if not Path(CONFIG_FILE).exists():
        save_config({})
    click.echo('初始化成功。issue 存储文件夹已创建。')

@cli.command()
@click.argument('repo')
def link(repo):
    config = load_config()
    config['repo'] = repo
    save_config(config)
    click.echo(f'已链接仓库：{repo}')

@cli.command()
@click.argument('token')
def token(token):
    config = load_config()
    config['token'] = token
    save_config(config)
    click.echo('Token 已保存。')

@cli.command()
@click.option('-t', '--title', prompt='Issue 标题', help='Issue 标题')
@click.option('-l', '--label', multiple=True, help='Issue 标签')
@click.option('-m', '--milestone', help='里程碑')
def create(title, label, milestone):
    config = load_config()
    files = sorted(Path(ISSUE_FOLDER).glob('*.md'))
    next_id = 1 + max([int(f.name.split('.')[0]) for f in files], default=0)
    filename = f"{next_id}.{title.replace(' ', '_')}.md"
    filepath = Path(ISSUE_FOLDER) / filename
    metadata = {
        'title': title,
        'labels': list(label),
        'milestone': milestone
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f'<!-- {json.dumps(metadata)} -->\n\n')
        f.write('# ' + title + '\n\n')
    click.echo(f'本地 issue 创建成功：{filename}')

@cli.command()
@click.argument('number', type=int)
def delete(number):
    try:
        issue_file = next(f for f in Path(ISSUE_FOLDER).glob(f'{number}.*.md'))
        issue_file.unlink()
        click.echo(f'已删除本地 issue {number}')
    except StopIteration:
        click.echo('未找到该 issue 文件')

@cli.command()
def push():
    config = load_config()
    token = config.get('token')
    repo = config.get('repo')
    if not token or not repo:
        click.echo('请先设置 token 和 repo')
        return

    headers = github_headers(token)
    for f in Path(ISSUE_FOLDER).glob('*.md'):
        with open(f, 'r', encoding='utf-8') as issue_file:
            lines = issue_file.readlines()
        if lines and lines[0].startswith('<!--'):
            metadata = json.loads(lines[0][4:-4].strip())
            body = ''.join(lines[2:])
            issue_data = {
                'title': metadata['title'],
                'body': body,
                'labels': metadata.get('labels', [])
            }
            if metadata.get('milestone'):
                issue_data['milestone'] = metadata['milestone']

            response = requests.post(f'{GITHUB_API_URL}/repos/{repo}/issues',
                                     headers=headers, json=issue_data)
            if response.status_code == 201:
                click.echo(f"成功推送 issue: {metadata['title']}")
            else:
                click.echo(f"推送失败: {f.name} - {response.status_code} {response.text}")

@cli.command()
def pull():
    config = load_config()
    token = config.get('token')
    repo = config.get('repo')
    if not token or not repo:
        click.echo('请先设置 token 和 repo')
        return

    headers = github_headers(token)
    page = 1
    while True:
        response = requests.get(f'{GITHUB_API_URL}/repos/{repo}/issues?state=all&page={page}',
                                headers=headers)
        if response.status_code != 200:
            click.echo(f'拉取失败: {response.status_code} {response.text}')
            break

        issues = response.json()
        if not issues:
            break
        for issue in issues:
            filename = f"{issue['number']}.{issue['title'].replace(' ', '_')}.md"
            filepath = Path(ISSUE_FOLDER) / filename
            metadata = {
                'title': issue['title'],
                'labels': [label['name'] for label in issue.get('labels', [])],
                'milestone': issue.get('milestone', {}).get('title') if issue.get('milestone') else None
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f'<!-- {json.dumps(metadata)} -->\n\n')
                f.write(issue['body'] or '')
            click.echo(f'拉取 issue: {filename}')
        page += 1

@cli.command()
@click.option('-r', '--remote', is_flag=True, help='列出远程 issue')
@click.option('-l', '--local', is_flag=True, help='列出本地 issue')
@click.option('-o', '--open', 'state', flag_value='open')
@click.option('-c', '--close', 'state', flag_value='closed')
@click.option('-q', '--query', help='关键字过滤')
def list(remote, local, state, query):
    config = load_config()
    if local or not remote:
        for f in Path(ISSUE_FOLDER).glob('*.md'):
            if query and query not in f.name:
                continue
            click.echo(f.name)
    elif remote:
        token = config.get('token')
        repo = config.get('repo')
        if not token or not repo:
            click.echo('请先设置 token 和 repo')
            return
        headers = github_headers(token)
        params = {'state': state} if state else {}
        response = requests.get(f'{GITHUB_API_URL}/repos/{repo}/issues', headers=headers, params=params)
        if response.status_code == 200:
            for issue in response.json():
                if query and query not in issue['title']:
                    continue
                click.echo(f"#{issue['number']} {issue['title']}")
        else:
            click.echo(f'请求失败: {response.status_code} {response.text}')

if __name__ == '__main__':
    cli()
