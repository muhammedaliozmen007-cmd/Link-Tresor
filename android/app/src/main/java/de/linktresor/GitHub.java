package de.linktresor;

import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/** Kleiner GitHub-Client für den Link-Tresor (Gegenstück zu app/github_api.py). */
public class GitHub {
    public static String API = "https://api.github.com";

    public static class GitHubError extends Exception {
        public GitHubError(String msg) {
            super(msg);
        }
    }

    public interface Progress {
        void update(long done, long total);
    }

    public final String token;
    public final String repo;
    public final String branch;

    public GitHub(String token, String repo, String branch) {
        this.token = token == null ? "" : token.trim();
        this.repo = trimSlashes(repo == null ? "" : repo.trim());
        this.branch = branch == null ? "" : branch.trim();
    }

    private static String trimSlashes(String s) {
        while (s.startsWith("/")) s = s.substring(1);
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        return s;
    }

    // ------------------------------------------------------------------ intern
    /** Antwort: JSONObject, JSONArray oder null (404 bei GET). */
    private Object request(String method, String path, JSONObject body) throws GitHubError {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(API + path).openConnection();
            try {
                c.setRequestMethod(method);
            } catch (java.net.ProtocolException e) {
                // Manche HttpURLConnection-Versionen kennen kein PATCH -> per POST + Override-Header
                c.setRequestMethod("POST");
                c.setRequestProperty("X-HTTP-Method-Override", method);
            }
            c.setConnectTimeout(30000);
            c.setReadTimeout(120000);
            c.setRequestProperty("Accept", "application/vnd.github+json");
            c.setRequestProperty("X-GitHub-Api-Version", "2022-11-28");
            c.setRequestProperty("User-Agent", "Link-Tresor-Android");
            if (!token.isEmpty()) c.setRequestProperty("Authorization", "Bearer " + token);
            if (body != null) {
                byte[] data = body.toString().getBytes(StandardCharsets.UTF_8);
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json");
                c.setFixedLengthStreamingMode(data.length);
                try (OutputStream out = c.getOutputStream()) {
                    out.write(data);
                }
            }
            int code = c.getResponseCode();
            if (code >= 400) {
                if (code == 404 && method.equals("GET")) return null;
                String msg = "";
                try {
                    msg = new JSONObject(readAll(c.getErrorStream())).optString("message", "");
                } catch (Exception ignored) {
                }
                throw new GitHubError("HTTP " + code + ": " + hint(code, msg));
            }
            String raw = readAll(c.getInputStream()).trim();
            if (raw.isEmpty()) return new JSONObject();
            return raw.startsWith("[") ? new JSONArray(raw) : new JSONObject(raw);
        } catch (GitHubError e) {
            throw e;
        } catch (IOException e) {
            throw new GitHubError("Keine Verbindung zu GitHub: " + e.getMessage());
        } catch (Exception e) {
            throw new GitHubError("Unerwartete Antwort von GitHub: " + e.getMessage());
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private static String hint(int code, String msg) {
        switch (code) {
            case 401: return "Token ungültig oder abgelaufen.";
            case 403: return "Keine Berechtigung – hat der Token den Haken bei „repo“?";
            case 404: return "Repository nicht gefunden oder Token hat keinen Zugriff.";
            case 409: return "Konflikt – bitte nochmal versuchen.";
            case 422: return "GitHub hat die Anfrage abgelehnt (evtl. Datei zu groß).";
            default: return msg.isEmpty() ? "Fehler" : msg;
        }
    }

    static String readAll(InputStream in) throws IOException {
        return new String(readBytes(in), StandardCharsets.UTF_8);
    }

    static byte[] readBytes(InputStream in) throws IOException {
        if (in == null) return new byte[0];
        try (InputStream is = in) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = is.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        }
    }

    static String quote(String s) {
        try {
            return URLEncoder.encode(s, "UTF-8").replace("+", "%20").replace("%2F", "/");
        } catch (Exception e) {
            return s;
        }
    }

    private String contentsPath(String path) {
        return "/repos/" + repo + "/contents/" + quote(path);
    }

    private String refQuery() {
        return branch.isEmpty() ? "" : "?ref=" + quote(branch);
    }

    // ---------------------------------------------------------------- Dateien
    /** Prüft Token + Repo. Gibt den Standard-Branch zurück. */
    public String check() throws GitHubError {
        Object info = request("GET", "/repos/" + repo, null);
        if (!(info instanceof JSONObject))
            throw new GitHubError("Repository nicht gefunden oder Token hat keinen Zugriff.");
        JSONObject o = (JSONObject) info;
        JSONObject perms = o.optJSONObject("permissions");
        if (perms == null || !perms.optBoolean("push", false))
            throw new GitHubError("Token hat keine Schreibrechte auf dieses Repository.");
        return o.optString("default_branch", "main");
    }

    /** Inhalt + sha einer Datei; null, wenn sie fehlt. */
    public static class FileData {
        public final byte[] data;
        public final String sha;

        FileData(byte[] data, String sha) {
            this.data = data;
            this.sha = sha;
        }

        public String text() {
            return new String(data, StandardCharsets.UTF_8);
        }
    }

    public FileData getFile(String path) throws GitHubError {
        Object info = request("GET", contentsPath(path) + refQuery(), null);
        if (!(info instanceof JSONObject)) return null;
        JSONObject o = (JSONObject) info;
        String content = o.optString("content", null);
        if (content == null || content.isEmpty() || !"base64".equals(o.optString("encoding"))) {
            // Große Dateien (>1 MB) liefert die API ohne Inhalt -> Blob holen
            Object blob = request("GET", "/repos/" + repo + "/git/blobs/" + o.optString("sha"), null);
            content = blob instanceof JSONObject ? ((JSONObject) blob).optString("content", "") : "";
        }
        return new FileData(Base64.decode(content, Base64.DEFAULT), o.optString("sha"));
    }

    public boolean exists(String path) throws GitHubError {
        return request("GET", contentsPath(path) + refQuery(), null) instanceof JSONObject;
    }

    public void putFile(String path, byte[] data, String message, String sha) throws GitHubError {
        try {
            JSONObject body = new JSONObject();
            body.put("message", message);
            body.put("content", Base64.encodeToString(data, Base64.NO_WRAP));
            if (sha != null) body.put("sha", sha);
            if (!branch.isEmpty()) body.put("branch", branch);
            request("PUT", contentsPath(path), body);
        } catch (org.json.JSONException e) {
            throw new GitHubError(e.getMessage());
        }
    }

    /** Einträge eines Ordners: Liste von {name, type}. */
    public List<JSONObject> listDir(String path) throws GitHubError {
        Object info = request("GET", contentsPath(path) + refQuery(), null);
        List<JSONObject> out = new ArrayList<>();
        if (info instanceof JSONArray) {
            JSONArray a = (JSONArray) info;
            for (int i = 0; i < a.length(); i++) out.add(a.optJSONObject(i));
        }
        return out;
    }

    public void deleteFile(String path, String message) throws GitHubError {
        Object info = request("GET", contentsPath(path) + refQuery(), null);
        if (!(info instanceof JSONObject)) return; // schon weg
        try {
            JSONObject body = new JSONObject();
            body.put("message", message);
            body.put("sha", ((JSONObject) info).optString("sha"));
            if (!branch.isEmpty()) body.put("branch", branch);
            request("DELETE", contentsPath(path), body);
        } catch (org.json.JSONException e) {
            throw new GitHubError(e.getMessage());
        }
    }

    public interface PathMap {
        /** Neuer Pfad oder null zum Löschen. */
        String map(String oldPath);
    }

    /** Ändert alle Dateien unter directory in einem einzigen Commit. */
    private void rewriteDir(String directory, String message, PathMap newPath) throws GitHubError {
        if (branch.isEmpty()) throw new GitHubError("Kein Branch eingestellt.");
        try {
            String git = "/repos/" + repo + "/git";
            String b = quote(branch);
            Object ref = request("GET", git + "/ref/heads/" + b, null);
            if (!(ref instanceof JSONObject)) throw new GitHubError("Branch „" + branch + "“ nicht gefunden.");
            String head = ((JSONObject) ref).getJSONObject("object").getString("sha");
            JSONObject commit = (JSONObject) request("GET", git + "/commits/" + head, null);
            String treeSha = commit.getJSONObject("tree").getString("sha");
            JSONObject tree = (JSONObject) request("GET", git + "/trees/" + treeSha + "?recursive=1", null);
            if (tree.optBoolean("truncated")) throw new GitHubError("Repository zu groß für diese Aktion.");

            String prefix = trimSlashes(directory) + "/";
            JSONArray changes = new JSONArray();
            JSONArray entries = tree.getJSONArray("tree");
            for (int i = 0; i < entries.length(); i++) {
                JSONObject e = entries.getJSONObject(i);
                String p = e.getString("path");
                if (!"blob".equals(e.optString("type")) || !p.startsWith(prefix)) continue;
                String target = newPath.map(p);
                if (target != null) {
                    changes.put(new JSONObject().put("path", target).put("mode", e.getString("mode"))
                            .put("type", "blob").put("sha", e.getString("sha")));
                }
                changes.put(new JSONObject().put("path", p).put("mode", e.getString("mode"))
                        .put("type", "blob").put("sha", JSONObject.NULL));
            }
            if (changes.length() == 0) throw new GitHubError("Der Ordner ist leer oder existiert nicht.");

            JSONObject newTree = (JSONObject) request("POST", git + "/trees",
                    new JSONObject().put("base_tree", tree.getString("sha")).put("tree", changes));
            JSONObject newCommit = (JSONObject) request("POST", git + "/commits",
                    new JSONObject().put("message", message).put("tree", newTree.getString("sha"))
                            .put("parents", new JSONArray().put(head)));
            request("PATCH", git + "/refs/heads/" + b, new JSONObject().put("sha", newCommit.getString("sha")));
        } catch (org.json.JSONException e) {
            throw new GitHubError("Unerwartete Antwort von GitHub: " + e.getMessage());
        }
    }

    public void moveDir(String oldDir, String newDir, String message) throws GitHubError {
        String oldPrefix = trimSlashes(oldDir) + "/", newPrefix = trimSlashes(newDir) + "/";
        rewriteDir(oldDir, message, p -> newPrefix + p.substring(oldPrefix.length()));
    }

    public void deleteDir(String directory, String message) throws GitHubError {
        rewriteDir(directory, message, p -> null);
    }

    public String repoUrl() {
        return "https://github.com/" + repo;
    }

    public String treeUrl(String path) {
        return repoUrl() + "/tree/" + (branch.isEmpty() ? "HEAD" : branch) + "/" + quote(path);
    }

    public String fileUrl(String path) {
        return repoUrl() + "/blob/" + (branch.isEmpty() ? "HEAD" : branch) + "/" + quote(path);
    }

    // --------------------------------------------------------------- Feedback
    public String createIssue(String title, String body, String... labels) throws GitHubError {
        String path = "/repos/" + repo + "/issues";
        try {
            JSONObject req = new JSONObject().put("title", title).put("body", body);
            JSONArray l = new JSONArray();
            for (String s : labels) l.put(s);
            Object res;
            try {
                res = request("POST", path, new JSONObject(req.toString()).put("labels", l));
            } catch (GitHubError e) {
                if (!e.getMessage().contains("422")) throw e;
                res = request("POST", path, req); // Labels abgelehnt -> ohne Labels
            }
            return res instanceof JSONObject ? ((JSONObject) res).optString("html_url", "") : "";
        } catch (org.json.JSONException e) {
            throw new GitHubError(e.getMessage());
        }
    }

    public static final String BELL_PREFIX = "🔔 Bitte umsetzen:";

    /** Nummer des offenen Feedback-Kanal-PRs (Branch feedback-kanal) oder 0. */
    int feedbackPr() throws GitHubError {
        String owner = repo.split("/")[0];
        Object pulls = request("GET", "/repos/" + repo + "/pulls?state=open&head="
                + quote(owner + ":feedback-kanal"), null);
        if (!(pulls instanceof JSONArray) || ((JSONArray) pulls).length() == 0) return 0;
        return ((JSONArray) pulls).optJSONObject(0).optInt("number");
    }

    /** Offene Feedback-Issues: {nummer, titel, "1" wenn schon gerufen sonst "0"}. */
    public List<String[]> openFeedback() throws GitHubError {
        Object res = request("GET", "/repos/" + repo + "/issues?state=open&labels=feedback&per_page=100", null);
        List<JSONObject> issues = new ArrayList<>();
        String since = null;
        if (res instanceof JSONArray) {
            JSONArray a = (JSONArray) res;
            for (int i = 0; i < a.length(); i++) {
                JSONObject o = a.optJSONObject(i);
                if (o == null || o.has("pull_request")) continue;
                issues.add(o);
                String c = o.optString("created_at", "");
                if (since == null || c.compareTo(since) < 0) since = c;
            }
        }
        java.util.Set<String> rung = new java.util.HashSet<>();
        int pr = issues.isEmpty() ? 0 : feedbackPr();
        if (pr > 0) {
            // Nur Klingel-Kommentare seit dem ältesten offenen Feedback ansehen
            Object cs = request("GET", "/repos/" + repo + "/issues/" + pr + "/comments?per_page=100&since="
                    + quote(since), null);
            if (cs instanceof JSONArray) {
                JSONArray a = (JSONArray) cs;
                for (int i = 0; i < a.length(); i++) {
                    String first = a.optJSONObject(i).optString("body", "").split("\n", 2)[0];
                    if (!first.startsWith(BELL_PREFIX)) continue;
                    java.util.regex.Matcher m = java.util.regex.Pattern.compile("#(\\d+)").matcher(first);
                    while (m.find()) rung.add(m.group(1));
                }
            }
        }
        List<String[]> out = new ArrayList<>();
        for (JSONObject o : issues) {
            String nr = String.valueOf(o.optInt("number"));
            out.add(new String[]{nr, o.optString("title"), rung.contains(nr) ? "1" : "0"});
        }
        return out;
    }

    /** Kommentiert im Feedback-Kanal -> weckt Claude. */
    public boolean ringBell(String text) throws GitHubError {
        int number = feedbackPr();
        if (number == 0) return false;
        try {
            request("POST", "/repos/" + repo + "/issues/" + number + "/comments", new JSONObject().put("body", text));
        } catch (org.json.JSONException e) {
            throw new GitHubError(e.getMessage());
        }
        return true;
    }

    // ----------------------------------------------------------------- Update
    public JSONObject release(String tag) throws GitHubError {
        Object r = request("GET", "/repos/" + repo + "/releases/tags/" + quote(tag), null);
        return r instanceof JSONObject ? (JSONObject) r : null;
    }

    /** Lädt ein Release-Asset (auch aus privaten Repos) nach dest. */
    public void downloadAsset(long assetId, java.io.File dest, Progress progress) throws GitHubError {
        String url = API + "/repos/" + repo + "/releases/assets/" + assetId;
        try {
            for (int hop = 0; hop < 5; hop++) {
                HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
                c.setInstanceFollowRedirects(false);
                c.setConnectTimeout(30000);
                c.setReadTimeout(120000);
                c.setRequestProperty("User-Agent", "Link-Tresor-Android");
                boolean github = new URL(API).getHost().equals(new URL(url).getHost());
                c.setRequestProperty("Accept", github ? "application/octet-stream" : "*/*");
                // Den Token nur an GitHub selbst schicken, nicht an den Speicher-Server
                if (github && !token.isEmpty()) c.setRequestProperty("Authorization", "Bearer " + token);
                int code = c.getResponseCode();
                if (code >= 300 && code < 400) {
                    url = c.getHeaderField("Location");
                    c.disconnect();
                    continue;
                }
                if (code >= 400) throw new GitHubError("Download fehlgeschlagen: HTTP " + code);
                long total = c.getContentLengthLong();
                try (InputStream in = c.getInputStream(); FileOutputStream out = new FileOutputStream(dest)) {
                    byte[] buf = new byte[256 * 1024];
                    long done = 0;
                    int n;
                    while ((n = in.read(buf)) > 0) {
                        out.write(buf, 0, n);
                        done += n;
                        if (progress != null) progress.update(done, total);
                    }
                }
                c.disconnect();
                return;
            }
            throw new GitHubError("Download fehlgeschlagen: zu viele Weiterleitungen");
        } catch (IOException e) {
            throw new GitHubError("Keine Verbindung zu GitHub: " + e.getMessage());
        }
    }
}
