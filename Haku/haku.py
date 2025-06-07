import os
import sys
import argparse
import configparser
import requests
import shutil
from datetime import datetime
from pathlib import Path

# 配置常量
CONFIG_FILE = ".hakuconfig"
ISSUES_DIR = "issues"
BACKUP_DIR = "backups"
GITHUB_API = "https://api.github.com"

class Haku:
    def __init__(self):
        self.config_path = Path(CONFIG_FILE)
        self.config = configparser.ConfigParser()
        self.session = requests.Session()
        self.setup()

    def setup(self):
        """初始化配置"""
        if not self.config_path.exists():
            self.config["DEFAULT"] = {
                "repo_owner": "",
                "repo_name": "",
                "token": ""
            }
            with open(self.config_path, "w") as configfile:
                self.config.write(configfile)
        else:
            self.config.read(self.config_path)
        
        # 设置API头
        token = self.config.get("DEFAULT", "token", fallback="")
        if token:
            self.session.headers.update({
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            })
        
        # 创建必要目录
        Path(ISSUES_DIR).mkdir(exist_ok=True)
        Path(BACKUP_DIR).mkdir(exist_ok=True)

    def init_repo(self):
        """初始化仓库"""
        if not Path(ISSUES_DIR).exists():
            Path(ISSUES_DIR).mkdir()
            print(f"Created '{ISSUES_DIR}' directory")
        print("Repository initialized")

    def link_repo(self, owner, name):
        """链接远程仓库"""
        self.config.set("DEFAULT", "repo_owner", owner)
        self.config.set("DEFAULT", "repo_name", name)
        with open(self.config_path, "w") as configfile:
            self.config.write(configfile)
        print(f"Linked to repository: {owner}/{name}")

    def create_issue(self, title=None, labels=None, milestone=None):
        """创建issue"""
        if not title:
            title = input("Enter issue title: ").strip()
            if not title:
                print("Title cannot be empty!")
                return
        
        issue_num = self._get_next_issue_number()
        clean_title = self._clean_filename(title)
        filename = f"{issue_num}.{clean_title}.md"
        filepath = Path(ISSUES_DIR) / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n")
            if labels:
                f.write(f"**Labels:** {', '.join(labels)}\n\n")
            if milestone:
                f.write(f"**Milestone:** {milestone}\n\n")
            f.write("<!-- Describe your issue here -->")
        
        print(f"Created issue #{issue_num}: {filepath}")

    def delete_issue(self, issue_num):
        """删除issue"""
        filepath = self._find_issue_file(issue_num)
        if not filepath:
            print(f"Issue #{issue_num} not found locally")
            return
        
        # 创建备份
        self._create_backup()
        os.remove(filepath)
        print(f"Deleted local issue #{issue_num}")

    def push_issues(self, dry_run=False):
        """推送issue到GitHub"""
        if dry_run:
            print("--- DRY RUN MODE ---")
        
        # 验证配置
        owner = self.config.get("DEFAULT", "repo_owner", fallback="")
        repo = self.config.get("DEFAULT", "repo_name", fallback="")
        token = self.config.get("DEFAULT", "token", fallback="")
        
        if not all([owner, repo, token]):
            print("Error: Missing repository configuration or token")
            return
        
        # 获取远程issue
        remote_issues = self._get_remote_issues()
        local_issues = self._get_local_issues()
        
        # 创建备份
        if not dry_run:
            self._create_backup()
        
        # 同步操作
        for issue_num, filepath in local_issues.items():
            # 从文件名中提取标题（去掉编号部分）
            title_part = filepath.stem.split(".", 1)[1]
            title = title_part.replace("_", " ")
            
            if issue_num in remote_issues:
                action = "Updating"
                url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_num}"
                method = "PATCH"
            else:
                action = "Creating"
                url = f"{GITHUB_API}/repos/{owner}/{repo}/issues"
                method = "POST"
            
            print(f"{action} issue #{issue_num}")
            
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            body = {"title": title, "body": content}
            
            if not dry_run:
                try:
                    response = self.session.request(method, url, json=body)
                    response.raise_for_status()
                    
                    # 对于新建的issue，更新本地文件名中的编号
                    if method == "POST":
                        new_issue_num = response.json()["number"]
                        new_filename = f"{new_issue_num}.{title_part}.md"
                        new_filepath = Path(ISSUES_DIR) / new_filename
                        os.rename(filepath, new_filepath)
                        print(f"Updated local issue number to #{new_issue_num}")
                except requests.exceptions.RequestException as e:
                    print(f"Error pushing issue #{issue_num}: {str(e)}")
        
        # 处理删除
        deleted_issues = set(remote_issues.keys()) - set(local_issues.keys())
        for issue_num in deleted_issues:
            print(f"Closing issue #{issue_num} (not found locally)")
            if not dry_run:
                try:
                    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_num}"
                    self.session.patch(url, json={"state": "closed"})
                except requests.exceptions.RequestException as e:
                    print(f"Error closing issue #{issue_num}: {str(e)}")
        
        print("Push completed!" if not dry_run else "Dry run completed")

    def pull_issues(self):
        """从GitHub拉取issue"""
        # 验证配置
        owner = self.config.get("DEFAULT", "repo_owner", fallback="")
        repo = self.config.get("DEFAULT", "repo_name", fallback="")
        
        if not all([owner, repo]):
            print("Error: Missing repository configuration")
            return
        
        # 创建备份
        self._create_backup()
        
        # 获取远程issue
        try:
            url = f"{GITHUB_API}/repos/{owner}/{repo}/issues"
            issues = self._get_all_pages(url, params={"state": "all"})
        except requests.exceptions.RequestException as e:
            print(f"Error fetching issues: {str(e)}")
            return
        
        # 保存issue
        for issue in issues:
            issue_num = issue["number"]
            title = issue["title"]
            clean_title = self._clean_filename(title)
            filename = f"{issue_num}.{clean_title}.md"
            filepath = Path(ISSUES_DIR) / filename
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(issue["body"] or "")
            
            print(f"Pulled issue #{issue_num}")
        
        print(f"Pulled {len(issues)} issues")

    def list_issues(self, remote=False, state=None, query=None):
        """列出issue"""
        if remote:
            self._list_remote_issues(state, query)
        else:
            self._list_local_issues(state, query)

    def set_token(self, token):
        """设置GitHub token"""
        self.config.set("DEFAULT", "token", token)
        with open(self.config_path, "w") as configfile:
            self.config.write(configfile)
        self.session.headers.update({"Authorization": f"token {token}"})
        print("Token set successfully")

    # 辅助方法
    def _clean_filename(self, title):
        """清理文件名中的非法字符"""
        invalid_chars = r'<>:"/\|?*'
        for char in invalid_chars:
            title = title.replace(char, '')
        return title.replace(' ', '_')

    def _get_next_issue_number(self):
        """获取下一个issue编号"""
        max_num = 0
        for file in Path(ISSUES_DIR).iterdir():
            if file.is_file() and file.suffix == ".md":
                parts = file.name.split(".", 1)
                if parts[0].isdigit():
                    num = int(parts[0])
                    if num > max_num:
                        max_num = num
        return max_num + 1

    def _find_issue_file(self, issue_num):
        """查找issue文件"""
        for file in Path(ISSUES_DIR).iterdir():
            if file.is_file() and file.suffix == ".md":
                parts = file.name.split(".", 1)
                if parts[0] == str(issue_num):
                    return file
        return None

    def _get_local_issues(self):
        """获取本地issue"""
        issues = {}
        for file in Path(ISSUES_DIR).iterdir():
            if file.is_file() and file.suffix == ".md":
                parts = file.name.split(".", 1)
                if parts[0].isdigit():
                    issues[int(parts[0])] = file
        return issues

    def _get_remote_issues(self):
        """获取远程issue编号映射"""
        owner = self.config.get("DEFAULT", "repo_owner", fallback="")
        repo = self.config.get("DEFAULT", "repo_name", fallback="")
        if not all([owner, repo]):
            return {}
        
        try:
            url = f"{GITHUB_API}/repos/{owner}/{repo}/issues"
            issues = self._get_all_pages(url, params={"state": "all"})
            return {issue["number"]: issue for issue in issues}
        except requests.exceptions.RequestException:
            return {}

    def _get_all_pages(self, url, params=None):
        """处理分页请求"""
        results = []
        while url:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            results.extend(response.json())
            
            # 检查分页
            if "next" in response.links:
                url = response.links["next"]["url"]
                params = None  # 分页URL已包含参数
            else:
                url = None
        return results

    def _create_backup(self):
        """创建备份"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = Path(BACKUP_DIR) / timestamp
        backup_path.mkdir(parents=True, exist_ok=True)
        
        for file in Path(ISSUES_DIR).iterdir():
            if file.is_file() and file.suffix == ".md":
                shutil.copy2(file, backup_path / file.name)
        
        print(f"Created backup: {backup_path}")

    def _list_local_issues(self, state=None, query=None):
        """列出本地issue"""
        print("\nLocal Issues:")
        print("=============")
        for file in sorted(Path(ISSUES_DIR).iterdir(), key=lambda f: f.name):
            if file.is_file() and file.suffix == ".md":
                parts = file.stem.split(".", 1)
                if len(parts) == 2 and parts[0].isdigit():
                    print(f"#{parts[0]}: {parts[1].replace('_', ' ')}")
        print()

    def _list_remote_issues(self, state=None, query=None):
        """列出远程issue"""
        owner = self.config.get("DEFAULT", "repo_owner", fallback="")
        repo = self.config.get("DEFAULT", "repo_name", fallback="")
        if not all([owner, repo]):
            print("Error: Missing repository configuration")
            return
        
        try:
            url = f"{GITHUB_API}/repos/{owner}/{repo}/issues"
            params = {"state": "all"}
            if state:
                params["state"] = state
            if query:
                # GitHub问题列表不支持query参数，这里只是示例
                print("Warning: Query parameter is not supported in remote list")
            
            issues = self._get_all_pages(url, params=params)
            
            print("\nRemote Issues:")
            print("==============")
            for issue in issues:
                state_icon = "✓" if issue["state"] == "closed" else " "
                print(f"[{state_icon}] #{issue['number']}: {issue['title']}")
            print()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching remote issues: {str(e)}")

def main():
    parser = argparse.ArgumentParser(prog="haku", description="Haku - GitHub Issue Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # init
    subparsers.add_parser("init", help="Initialize repository")
    
    # link
    link_parser = subparsers.add_parser("link", help="Link remote repository")
    link_parser.add_argument("owner", help="Repository owner")
    link_parser.add_argument("repo", help="Repository name")
    
    # create
    create_parser = subparsers.add_parser("create", help="Create new issue")
    create_parser.add_argument("-t", "--title", help="Issue title")
    create_parser.add_argument("-l", "--label", action="append", help="Add label")
    create_parser.add_argument("-m", "--milestone", help="Set milestone")
    
    # delete
    delete_parser = subparsers.add_parser("delete", help="Delete local issue")
    delete_parser.add_argument("issue_num", type=int, help="Issue number")
    
    # push
    push_parser = subparsers.add_parser("push", help="Push issues to GitHub")
    push_parser.add_argument("--dry-run", action="store_true", help="Simulate without changes")
    
    # pull
    subparsers.add_parser("pull", help="Pull issues from GitHub")
    
    # list
    list_parser = subparsers.add_parser("list", help="List issues")
    list_parser.add_argument("-r", "--remote", action="store_true", help="List remote issues")
    list_parser.add_argument("-l", "--local", action="store_true", help="List local issues")
    list_parser.add_argument("-o", "--open", action="store_true", help="Filter open issues")
    list_parser.add_argument("-c", "--closed", action="store_true", help="Filter closed issues")
    list_parser.add_argument("-q", "--query", help="Search query")
    
    # token
    token_parser = subparsers.add_parser("token", help="Set GitHub token")
    token_parser.add_argument("token", help="GitHub access token")
    
    args = parser.parse_args()
    haku = Haku()
    
    try:
        if args.command == "init":
            haku.init_repo()
        
        elif args.command == "link":
            haku.link_repo(args.owner, args.repo)
        
        elif args.command == "create":
            haku.create_issue(args.title, args.label, args.milestone)
        
        elif args.command == "delete":
            haku.delete_issue(args.issue_num)
        
        elif args.command == "push":
            haku.push_issues(args.dry_run)
        
        elif args.command == "pull":
            haku.pull_issues()
        
        elif args.command == "list":
            state = None
            if args.open:
                state = "open"
            elif args.closed:
                state = "closed"
            haku.list_issues(args.remote, state, args.query)
        
        elif args.command == "token":
            haku.set_token(args.token)
    
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()