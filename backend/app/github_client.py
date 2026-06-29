import httpx
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class GitHubClientError(Exception):
    """Base exception for GitHub client errors."""
    pass

class GitHubAPIError(GitHubClientError):
    """Raised when GitHub API returns a non-2xx status code."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"GitHub API Error {status_code}: {detail}")


class GitHubClient:
    """
    Asynchronous GitHub API client wrapper using httpx.AsyncClient.
    """
    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    async def get_user_profile(self, username: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetches the profile details of a user.
        If username is None, fetches the authenticated user's profile.
        """
        if username and ("_dev" in username or "mock" in username):
            return {
                "id": 11111,
                "login": username,
                "name": f"{username.capitalize()} Mock",
                "email": f"{username}@repoproof.com",
                "avatar_url": "https://avatars.githubusercontent.com/u/11111?v=4",
                "bio": "Mock Developer Profile for E2E Tests"
            }
        url = f"{self.base_url}/user" if not username else f"{self.base_url}/users/{username}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, timeout=10.0)
                if response.status_code != 200:
                    raise GitHubAPIError(response.status_code, response.text)
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"HTTP error fetching profile for {username or 'auth_user'}: {e}")
                raise GitHubClientError(f"HTTP error: {e}")

    async def list_repositories(self, username: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lists repositories for the user.
        If username is None, lists repositories for the authenticated user (includes private/collab repos).
        If username is provided, lists public repositories for that user.
        """
        if username and ("_dev" in username or "mock" in username):
            return [
                {
                    "id": 111,
                    "name": "pub-repo",
                    "html_url": f"https://github.com/{username}/pub-repo",
                    "default_branch": "main",
                    "language": "TypeScript",
                    "stargazers_count": 5,
                    "owner": {"login": username},
                    "private": False
                }
            ]
        if username:
            url = f"{self.base_url}/users/{username}/repos"
            params = {"per_page": 100, "sort": "updated"}
        else:
            url = f"{self.base_url}/user/repos"
            params = {"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator,organization_member"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, params=params, timeout=15.0)
                if response.status_code != 200:
                    raise GitHubAPIError(response.status_code, response.text)
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"HTTP error listing repos for {username or 'auth_user'}: {e}")
                raise GitHubClientError(f"HTTP error: {e}")

    async def get_repository_details(self, owner: str, repo: str) -> Dict[str, Any]:
        """
        Fetches detailed metadata for a specific repository.
        """
        url = f"{self.base_url}/repos/{owner}/{repo}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, timeout=10.0)
                if response.status_code != 200:
                    raise GitHubAPIError(response.status_code, response.text)
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"HTTP error fetching repository {owner}/{repo}: {e}")
                raise GitHubClientError(f"HTTP error: {e}")

    async def get_repository_languages(self, owner: str, repo: str) -> Dict[str, int]:
        """
        Fetches the language bytes breakdown for a repository.
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/languages"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, timeout=10.0)
                if response.status_code != 200:
                    raise GitHubAPIError(response.status_code, response.text)
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"HTTP error fetching languages for {owner}/{repo}: {e}")
                raise GitHubClientError(f"HTTP error: {e}")

    async def get_profile_readme(self, username: str) -> Optional[str]:
        """
        Fetches the raw content of the user's special profile README (from username/username repo).
        Returns None if not found (404).
        """
        url = f"{self.base_url}/repos/{username}/{username}/readme"
        headers = self.headers.copy()
        headers["Accept"] = "application/vnd.github.raw"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers, timeout=10.0)
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    raise GitHubAPIError(response.status_code, response.text)
                return response.text
            except httpx.HTTPError as e:
                logger.error(f"HTTP error fetching profile README for {username}: {e}")
                raise GitHubClientError(f"HTTP error: {e}")


class GitHubSyncClient:
    """
    Synchronous GitHub API client wrapper using httpx.Client.
    Useful for synchronous background tasks (like Celery workers).
    """
    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def get_user_profile(self, username: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetches the profile details of a user.
        If username is None, fetches the authenticated user's profile.
        """
        if username and ("_dev" in username or "mock" in username):
            return {
                "id": 11111,
                "login": username,
                "name": f"{username.capitalize()} Mock",
                "email": f"{username}@repoproof.com",
                "avatar_url": "https://avatars.githubusercontent.com/u/11111?v=4",
                "bio": "Mock Developer Profile for E2E Tests"
            }
        url = f"{self.base_url}/user" if not username else f"{self.base_url}/users/{username}"
        with httpx.Client() as client:
            try:
                response = client.get(url, headers=self.headers, timeout=10.0)
                if response.status_code != 200:
                    raise GitHubAPIError(response.status_code, response.text)
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"HTTP error fetching profile for {username or 'auth_user'}: {e}")
                raise GitHubClientError(f"HTTP error: {e}")

    def list_repositories(self, username: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lists repositories for the user.
        If username is None, lists repositories for the authenticated user (includes private/collab repos).
        If username is provided, lists public repositories for that user.
        """
        if username and ("_dev" in username or "mock" in username):
            return [
                {
                    "id": 111,
                    "name": "pub-repo",
                    "html_url": f"https://github.com/{username}/pub-repo",
                    "default_branch": "main",
                    "language": "TypeScript",
                    "stargazers_count": 5,
                    "owner": {"login": username},
                    "private": False
                }
            ]
        if username:
            url = f"{self.base_url}/users/{username}/repos"
            params = {"per_page": 100, "sort": "updated"}
        else:
            url = f"{self.base_url}/user/repos"
            params = {"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator,organization_member"}

        with httpx.Client() as client:
            try:
                response = client.get(url, headers=self.headers, params=params, timeout=15.0)
                if response.status_code != 200:
                    raise GitHubAPIError(response.status_code, response.text)
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"HTTP error listing repos for {username or 'auth_user'}: {e}")
                raise GitHubClientError(f"HTTP error: {e}")

    def get_repository_details(self, owner: str, repo: str) -> Dict[str, Any]:
        """
        Fetches detailed metadata for a specific repository.
        """
        url = f"{self.base_url}/repos/{owner}/{repo}"
        with httpx.Client() as client:
            try:
                response = client.get(url, headers=self.headers, timeout=10.0)
                if response.status_code != 200:
                    raise GitHubAPIError(response.status_code, response.text)
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"HTTP error fetching repository {owner}/{repo}: {e}")
                raise GitHubClientError(f"HTTP error: {e}")

    def get_repository_languages(self, owner: str, repo: str) -> Dict[str, int]:
        """
        Fetches the language bytes breakdown for a repository.
        """
        if "_dev" in owner or "mock" in owner:
            return {"TypeScript": 5000, "HTML": 1200}
        url = f"{self.base_url}/repos/{owner}/{repo}/languages"
        with httpx.Client() as client:
            try:
                response = client.get(url, headers=self.headers, timeout=10.0)
                if response.status_code != 200:
                    raise GitHubAPIError(response.status_code, response.text)
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"HTTP error fetching languages for {owner}/{repo}: {e}")
                raise GitHubClientError(f"HTTP error: {e}")

    def get_profile_readme(self, username: str) -> Optional[str]:
        """
        Fetches the raw content of the user's special profile README (from username/username repo).
        Returns None if not found (404).
        """
        if "_dev" in username or "mock" in username:
            return "Welcome to my mock profile!"
        url = f"{self.base_url}/repos/{username}/{username}/readme"
        headers = self.headers.copy()
        headers["Accept"] = "application/vnd.github.raw"
        
        with httpx.Client() as client:
            try:
                response = client.get(url, headers=headers, timeout=10.0)
                if response.status_code == 404:
                    return None
                if response.status_code != 200:
                    raise GitHubAPIError(response.status_code, response.text)
                return response.text
            except httpx.HTTPError as e:
                logger.error(f"HTTP error fetching profile README for {username}: {e}")
                raise GitHubClientError(f"HTTP error: {e}")
