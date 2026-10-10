"""Small stdlib-only GitHub client; never print tokens or response bodies on error."""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from common import strict_json


class APIError(RuntimeError):
    def __init__(self, code, path):
        self.code = code
        super().__init__(f"GitHub HTTP {code}: {path.split('?')[0]}")


class GitHub:
    def __init__(self, repo=None, token=None):
        self.repo = repo or os.environ["GITHUB_REPOSITORY"]
        self.token = token or os.environ["GH_TOKEN"]
        if self.repo != "Wang106/SoftwareLifeCycle":
            raise ValueError("Unexpected repository")
        self.root = "repos/" + self.repo

    def request(self, path, method="GET", data=None):
        if path.startswith(("https:", "http:", "/")):
            raise ValueError("API path must be relative")
        request = urllib.request.Request(
            "https://api.github.com/" + path,
            data=None if data is None else json.dumps(data).encode(),
            method=method,
            headers={"Authorization": "Bearer " + self.token,
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            raise APIError(error.code, path) from None

    def get(self, suffix, **params):
        query = "?" + urllib.parse.urlencode(params) if params else ""
        return self.request(self.root + "/" + suffix + query)

    def mutate(self, suffix, method, data):
        return self.request(self.root + "/" + suffix, method, data)

    def pages(self, suffix, key=None, **params):
        result = []
        for page in range(1, 21):
            data = self.get(suffix, per_page=100, page=page, **params)
            rows = data[key] if key else data
            result.extend(rows)
            if len(rows) < 100:
                return result
        raise ValueError("Pagination limit exceeded; refusing incomplete evidence")

    def ref(self, branch):
        return self.get("git/ref/heads/" + branch)["object"]["sha"]


class StateStore:
    branch = "codex-state"
    path = "automation-state.json"

    def __init__(self, api):
        self.api = api
        self.version = None

    def load(self, main_sha):
        try:
            self.api.ref(self.branch)
        except APIError as error:
            if error.code != 404:
                raise
            self.api.mutate("git/refs", "POST", {"ref": "refs/heads/" + self.branch, "sha": main_sha})
        try:
            data = self.api.get("contents/" + self.path, ref=self.branch)
        except APIError as error:
            if error.code != 404:
                raise
            return {"schema": 1, "tasks": {}, "daily": {}, "events": []}
        self.version = data["sha"]
        state = strict_json(base64.b64decode(data["content"]).decode())
        if state.get("schema") != 1 or not isinstance(state.get("tasks"), dict):
            raise ValueError("Invalid durable state")
        return state

    def save(self, state):
        state["events"] = state["events"][-50:]
        payload = {"message": "chore: checkpoint Codex scheduler state",
                   "branch": self.branch,
                   "content": base64.b64encode((json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode()).decode()}
        if self.version:
            payload["sha"] = self.version
        data = self.api.mutate("contents/" + self.path, "PUT", payload)
        self.version = data["content"]["sha"]
