"""Kleiner GitHub-Client (nur Standardbibliothek) für den Link-Tresor.

Schreibt Dateien über die GitHub Contents API direkt in ein Repository.
Jede Aktion erzeugt genau einen Commit.
"""

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
BELL_PREFIX = "🔔 Bitte umsetzen:"


class GitHubError(Exception):
    pass


class GitHubClient:
    def __init__(self, token, repo, branch=""):
        self.token = token.strip()
        self.repo = repo.strip().strip("/")
        self.branch = branch.strip()

    # ------------------------------------------------------------------ intern
    def _request(self, method, path, body=None):
        url = API + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "Link-Tresor")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 404 and method == "GET":
                return None
            try:
                msg = json.loads(e.read()).get("message", "")
            except Exception:
                msg = ""
            hints = {
                401: "Token ungültig oder abgelaufen.",
                403: "Keine Berechtigung – hat der Token Schreibrechte (Contents: Read and write)?",
                404: "Repository nicht gefunden oder Token hat keinen Zugriff.",
                409: "Konflikt – bitte nochmal versuchen.",
                422: "GitHub hat die Anfrage abgelehnt (evtl. Datei zu groß).",
            }
            raise GitHubError(f"HTTP {e.code}: {hints.get(e.code, msg or e.reason)}") from e
        except urllib.error.URLError as e:
            raise GitHubError(f"Keine Verbindung zu GitHub: {e.reason}") from e

    def _contents_path(self, path):
        return f"/repos/{self.repo}/contents/" + urllib.parse.quote(path)

    def _ref_query(self):
        return "?ref=" + urllib.parse.quote(self.branch) if self.branch else ""

    # ---------------------------------------------------------------- öffentlich
    def check(self):
        """Prüft Token + Repo. Gibt den Standard-Branch zurück."""
        info = self._request("GET", f"/repos/{self.repo}")
        if info is None:
            raise GitHubError("Repository nicht gefunden oder Token hat keinen Zugriff.")
        if not info.get("permissions", {}).get("push", False):
            raise GitHubError("Token hat keine Schreibrechte auf dieses Repository.")
        return info.get("default_branch", "main")

    def get_file(self, path):
        """Gibt (bytes, sha) zurück oder (None, None), wenn die Datei fehlt."""
        info = self._request("GET", self._contents_path(path) + self._ref_query())
        if not info or isinstance(info, list):
            return None, None
        content = info.get("content")
        if content is None or info.get("encoding") != "base64":
            # Große Dateien (>1 MB) liefert die API ohne Inhalt -> Blob holen
            blob = self._request("GET", f"/repos/{self.repo}/git/blobs/{info['sha']}")
            content = blob["content"]
        return base64.b64decode(content), info["sha"]

    def exists(self, path):
        info = self._request("GET", self._contents_path(path) + self._ref_query())
        return bool(info) and not isinstance(info, list)

    def put_file(self, path, data, message, sha=None):
        body = {
            "message": message,
            "content": base64.b64encode(data).decode("ascii"),
        }
        if sha:
            body["sha"] = sha
        if self.branch:
            body["branch"] = self.branch
        result = self._request("PUT", self._contents_path(path), body)
        return result.get("content", {}).get("html_url", "")

    def list_dir(self, path):
        info = self._request("GET", self._contents_path(path) + self._ref_query())
        return info if isinstance(info, list) else []

    def repo_url(self, path=""):
        url = f"https://github.com/{self.repo}"
        if path:
            url += f"/tree/{self.branch or 'HEAD'}/" + urllib.parse.quote(path)
        return url

    def delete_file(self, path, message, sha=None):
        if sha is None:
            info = self._request("GET", self._contents_path(path) + self._ref_query())
            if not info or isinstance(info, list):
                return  # schon weg
            sha = info["sha"]
        body = {"message": message, "sha": sha}
        if self.branch:
            body["branch"] = self.branch
        self._request("DELETE", self._contents_path(path), body)

    def _rewrite_dir(self, directory, message, new_path):
        """Ändert alle Dateien unter directory in einem einzigen Commit.

        new_path(alter_pfad) gibt den neuen Pfad zurück oder None zum Löschen.
        """
        if not self.branch:
            raise GitHubError("Kein Branch eingestellt.")
        repo = f"/repos/{self.repo}/git"
        branch = urllib.parse.quote(self.branch)
        ref = self._request("GET", f"{repo}/ref/heads/{branch}")
        if not ref:
            raise GitHubError(f"Branch „{self.branch}“ nicht gefunden.")
        head = ref["object"]["sha"]
        commit = self._request("GET", f"{repo}/commits/{head}")
        tree = self._request("GET", f"{repo}/trees/{commit['tree']['sha']}?recursive=1")
        if tree.get("truncated"):
            raise GitHubError("Repository zu groß für diese Aktion.")

        prefix = directory.rstrip("/") + "/"
        changes = []
        for e in tree["tree"]:
            if e["type"] == "blob" and e["path"].startswith(prefix):
                target = new_path(e["path"])
                if target:
                    changes.append({"path": target, "mode": e["mode"], "type": "blob", "sha": e["sha"]})
                changes.append({"path": e["path"], "mode": e["mode"], "type": "blob", "sha": None})
        if not changes:
            raise GitHubError("Der Ordner ist leer oder existiert nicht.")

        new_tree = self._request("POST", f"{repo}/trees", {"base_tree": tree["sha"], "tree": changes})
        new_commit = self._request(
            "POST", f"{repo}/commits", {"message": message, "tree": new_tree["sha"], "parents": [head]}
        )
        self._request("PATCH", f"{repo}/refs/heads/{branch}", {"sha": new_commit["sha"]})

    def move_dir(self, old_dir, new_dir, message):
        """Verschiebt alle Dateien von old_dir nach new_dir – in einem einzigen Commit."""
        old_prefix, new_prefix = old_dir.rstrip("/") + "/", new_dir.rstrip("/") + "/"
        self._rewrite_dir(old_dir, message, lambda p: new_prefix + p[len(old_prefix):])

    def delete_dir(self, directory, message):
        """Löscht alle Dateien unter directory – in einem einzigen Commit."""
        self._rewrite_dir(directory, message, lambda p: None)

    def file_url(self, path):
        return f"https://github.com/{self.repo}/blob/{self.branch or 'HEAD'}/" + urllib.parse.quote(path)

    # ------------------------------------------------------------- Feedback
    def create_issue(self, title, body, labels=()):
        path = f"/repos/{self.repo}/issues"
        try:
            result = self._request("POST", path, {"title": title, "body": body, "labels": list(labels)})
        except GitHubError as e:
            if not labels or "422" not in str(e):
                raise
            # Labels abgelehnt -> ohne Labels erneut versuchen
            result = self._request("POST", path, {"title": title, "body": body})
        return result.get("html_url", "")

    def _feedback_pr(self, branch="feedback-kanal"):
        """Nummer des offenen Feedback-Kanal-PRs (oder None)."""
        owner = self.repo.split("/")[0]
        query = urllib.parse.urlencode({"state": "open", "head": f"{owner}:{branch}"})
        pulls = self._request("GET", f"/repos/{self.repo}/pulls?{query}") or []
        return pulls[0]["number"] if pulls else None

    def ring_bell(self, text):
        """Kommentiert im offenen Pull Request des Feedback-Kanals -> weckt Claude.

        Gibt True zurück, wenn geklingelt wurde (False, wenn es keinen Kanal gibt).
        """
        number = self._feedback_pr()
        if not number:
            return False
        self._request("POST", f"/repos/{self.repo}/issues/{number}/comments", {"body": text})
        return True

    def open_feedback(self):
        """Offene Feedback-Issues -> Liste von (nummer, titel, schon_gerufen)."""
        query = urllib.parse.urlencode({"state": "open", "labels": "feedback", "per_page": 100})
        issues = [i for i in self._request("GET", f"/repos/{self.repo}/issues?{query}") or [] if "pull_request" not in i]
        rung = set()
        pr = self._feedback_pr() if issues else None
        if pr:
            # Nur Klingel-Kommentare seit dem ältesten offenen Feedback ansehen
            since = min(i["created_at"] for i in issues)
            query = urllib.parse.urlencode({"since": since, "per_page": 100})
            for c in self._request("GET", f"/repos/{self.repo}/issues/{pr}/comments?{query}") or []:
                first = (c.get("body") or "").split("\n", 1)[0]
                if first.startswith(BELL_PREFIX):
                    rung.update(int(n) for n in re.findall(r"#(\d+)", first))
        return [(i["number"], i["title"], i["number"] in rung) for i in issues]

    # --------------------------------------------------------------- Update
    def latest_release(self, tag="latest"):
        """Gibt das Release-Objekt zum Tag zurück (oder None)."""
        return self._request("GET", f"/repos/{self.repo}/releases/tags/{urllib.parse.quote(tag)}")

    def download_asset(self, asset_id, dest_path, progress=None):
        """Lädt ein Release-Asset (auch aus privaten Repos) nach dest_path."""
        req = urllib.request.Request(f"{API}/repos/{self.repo}/releases/assets/{asset_id}")
        req.add_header("Accept", "application/octet-stream")
        req.add_header("User-Agent", "Link-Tresor")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        opener = urllib.request.build_opener(_StripAuthOnRedirect)
        try:
            with opener.open(req, timeout=120) as resp, open(dest_path, "wb") as out:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        except urllib.error.HTTPError as e:
            raise GitHubError(f"Download fehlgeschlagen: HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise GitHubError(f"Keine Verbindung zu GitHub: {e.reason}") from e


class _StripAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """GitHub leitet Downloads an einen Speicher-Server weiter, der den Token nicht
    bekommen darf (sonst Fehler 400) – Authorization bei fremdem Host entfernen."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlparse(newurl).hostname != "api.github.com":
            new.headers.pop("Authorization", None)
            new.unredirected_hdrs.pop("Authorization", None)
            new.headers["Accept"] = "*/*"
        return new
