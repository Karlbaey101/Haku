import requests
from typing import List, Dict, Optional
from .models import Issue, Config
from .utils import extract_repo_info

class GitHubAPI:
    def __init__(self, config: Config):
        self.config = config
        self.owner, self.repo = extract_repo_info(config.repo_url)
        self.base_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/issues"
        self.headers = {
            "Authorization": f"token {config.token}",
            "Accept": "application/vnd.github.v3+json"
        }
    
    def _handle_response(self, response):
        if response.status_code in (200, 201):
            return response.json()
        else:
            error = response.json().get('message', 'Unknown error')
            raise Exception(f"GitHub API error ({response.status_code}): {error}")
    
    def create_issue(self, issue: Issue) -> dict:
        data = {
            "title": issue.title,
            "body": issue.body,
        }
        
        if issue.labels:
            data["labels"] = issue.labels # type: ignore
        
        if issue.milestone:
            data["milestone"] = issue.milestone
        
        response = requests.post(
            self.base_url,
            headers=self.headers,
            json=data
        )
        
        return self._handle_response(response)
    
    def update_issue(self, issue: Issue) -> dict:
        data = {
            "title": issue.title,
            "body": issue.body,
            "state": issue.state
        }
        
        if issue.labels:
            data["labels"] = issue.labels # type: ignore
        
        if issue.milestone:
            data["milestone"] = issue.milestone
        
        response = requests.patch(
            f"{self.base_url}/{issue.number}",
            headers=self.headers,
            json=data
        )
        
        return self._handle_response(response)
    
    def get_issue(self, number: int) -> dict:
        response = requests.get(
            f"{self.base_url}/{number}",
            headers=self.headers
        )
        return self._handle_response(response)
    
    def list_issues(self, state: str = "all", query: str = None) -> List[dict]: # type: ignore
        params = {"state": state}
        
        if query:
            params["q"] = f"{query} in:title,body"
        
        response = requests.get(
            self.base_url,
            headers=self.headers,
            params=params
        )
        
        return self._handle_response(response)
    
    def delete_issue(self, number: int):
        data = {"state": "closed"}
        response = requests.patch(
            f"{self.base_url}/{number}",
            headers=self.headers,
            json=data
        )
        return self._handle_response(response)