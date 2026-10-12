package de.linktresor;

import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Ablage-Logik (Gegenstück zu app/tresor.py – gleiches Format im Repo).
 *
 * Ordner „Allgemein“ = tresor/links.md, tresor/notizen/, tresor/dateien/
 * eigene Ordner     = tresor/<Name>/links.md, …/notizen/, …/dateien/
 */
public class Tresor {
    public static final String ROOT = "tresor";
    public static final String DEFAULT_FOLDER = "Allgemein";
    static final List<String> RESERVED = Arrays.asList("notizen", "dateien", "links.md", "allgemein");
    static final String KEEP_FILE = ".gitkeep";
    static final String LINKS_HEADER = "# Links\n\n<!-- Neue Einträge werden automatisch oben eingefügt -->\n";
    public static final long MAX_FILE_BYTES = 70L * 1024 * 1024;

    static final Pattern LINK_RE = Pattern.compile("^- \\[(.*?)(?<!\\\\)\\]\\((?:<([^>]+)>|([^)\\s]+))\\)");
    static final Pattern NOTE_RE = Pattern.compile("(\\d{4})-(\\d{2})-(\\d{2})_(\\d{2})(\\d{2})\\d{2}_(.*)\\.md$");
    static final Pattern BAD_CHARS = Pattern.compile("[\\\\/:*?\"<>|\\x00-\\x1f]");

    public static class Link {
        public final String title, url, line;

        Link(String title, String url, String line) {
            this.title = title;
            this.url = url;
            this.line = line;
        }
    }

    /** Notiz oder Datei: Anzeigename + Pfad im Repo. */
    public static class Entry {
        public final String label, path;

        Entry(String label, String path) {
            this.label = label;
            this.path = path;
        }
    }

    // ------------------------------------------------------------- Helfer
    static String now() {
        return new SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.GERMANY).format(new Date());
    }

    static String slugify(String text, String fallback) {
        text = text.trim().toLowerCase(Locale.ROOT)
                .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss");
        text = text.replaceAll("[^a-z0-9]+", "-").replaceAll("^-+|-+$", "");
        if (text.length() > 60) text = text.substring(0, 60);
        return text.isEmpty() ? fallback : text;
    }

    static String safeFilename(String name) {
        int slash = Math.max(name.lastIndexOf('/'), name.lastIndexOf('\\'));
        name = name.substring(slash + 1);
        name = BAD_CHARS.matcher(name).replaceAll("_").replaceAll("^[ .]+|[ .]+$", "");
        return name.isEmpty() ? "datei" : name;
    }

    public static String folderDir(String folder) {
        if (folder == null || folder.isEmpty() || folder.equals(DEFAULT_FOLDER)) return ROOT;
        return ROOT + "/" + folder;
    }

    public static String validateFolderName(String name, List<String> existing) {
        name = name.trim().replaceAll("\\s+", " ");
        if (name.isEmpty()) throw new IllegalArgumentException("Bitte einen Ordnernamen eingeben.");
        if (name.length() > 50) throw new IllegalArgumentException("Der Name ist zu lang (max. 50 Zeichen).");
        if (BAD_CHARS.matcher(name).find() || name.startsWith("."))
            throw new IllegalArgumentException("Der Name darf diese Zeichen nicht enthalten: \\ / : * ? \" < > |");
        if (RESERVED.contains(name.toLowerCase(Locale.ROOT)))
            throw new IllegalArgumentException("„" + name + "“ ist reserviert – bitte einen anderen Namen wählen.");
        for (String e : existing)
            if (e.equalsIgnoreCase(name)) throw new IllegalArgumentException("Den Ordner „" + name + "“ gibt es schon.");
        return name;
    }

    /** 2026-10-09_153914_keys.md -> "keys · 09.10.26 15:39" */
    static String noteLabel(String filename) {
        Matcher m = NOTE_RE.matcher(filename);
        if (!m.matches()) return filename;
        return m.group(6).replace('-', ' ') + " · " + m.group(3) + "." + m.group(2) + "."
                + m.group(1).substring(2) + " " + m.group(4) + ":" + m.group(5);
    }

    public static String normalizeUrl(String url) {
        url = url.trim();
        if (!url.isEmpty() && !url.matches("^[a-zA-Z][a-zA-Z0-9+.-]*:.*")) url = "https://" + url;
        return url;
    }

    static String mdEscape(String t) {
        return t.replace("[", "\\[").replace("]", "\\]").replace("\n", " ");
    }

    static String formatLinkLine(String url, String title, String note) {
        return formatLinkLine(url, title, note, null);
    }

    static String formatLinkLine(String url, String title, String note, String stamp) {
        String label = title.trim().isEmpty() ? url : mdEscape(title.trim());
        String line = "- [" + label + "](<" + url + ">)";
        if (!note.trim().isEmpty()) line += " — " + mdEscape(note.trim());
        return line + " · `" + (stamp == null || stamp.isEmpty() ? now() : stamp) + "`";
    }

    static final Pattern LINK_TAIL_RE = Pattern.compile("^(?: — (.*?))?(?: · `([^`]*)`)?\\s*$");

    /** Zerlegt eine Link-Zeile -> {titel, url, notiz, zeitstempel} oder null. */
    public static String[] parseLinkLine(String line) {
        Matcher m = LINK_RE.matcher(line);
        if (!m.find()) return null;
        String title = m.group(1).replace("\\[", "[").replace("\\]", "]");
        String url = m.group(2) != null ? m.group(2) : m.group(3);
        Matcher t = LINK_TAIL_RE.matcher(line.substring(m.end()));
        String note = "", stamp = "";
        if (t.matches()) {
            note = t.group(1) == null ? "" : t.group(1).replace("\\[", "[").replace("\\]", "]");
            stamp = t.group(2) == null ? "" : t.group(2);
        }
        return new String[]{title.equals(url) ? "" : title, url, note, stamp};
    }

    static final Pattern NOTE_FILE_RE = Pattern.compile("^# (.*)\\n\\n_([^_\\n]*)_\\n\\n(.*?)\\n?$", Pattern.DOTALL);

    /** Zerlegt eine Notiz-Datei -> {titel, zeitstempel, text}. */
    public static String[] parseNote(String md) {
        Matcher m = NOTE_FILE_RE.matcher(md.replace("\r\n", "\n"));
        if (!m.matches()) return new String[]{"", "", md.trim()};
        return new String[]{m.group(1).trim(), m.group(2), m.group(3).trim()};
    }

    static String replaceLine(String md, String old, String neu) {
        List<String> lines = splitLines(md);
        int i = lines.indexOf(old);
        if (i < 0) return null;
        lines.set(i, neu);
        return String.join("\n", lines) + "\n";
    }

    static List<String> splitLines(String s) {
        List<String> lines = new ArrayList<>(Arrays.asList(s.split("\r?\n", -1)));
        if (!lines.isEmpty() && lines.get(lines.size() - 1).isEmpty()) lines.remove(lines.size() - 1);
        return lines;
    }

    static String insertLink(String md, String line) {
        if (md == null || md.trim().isEmpty()) return LINKS_HEADER + "\n" + line + "\n";
        List<String> lines = splitLines(md);
        int i = 0;
        while (i < lines.size() && (lines.get(i).trim().isEmpty() || lines.get(i).startsWith("#")
                || lines.get(i).startsWith("<!--"))) i++;
        lines.add(i, line);
        if (i > 0 && !lines.get(i - 1).trim().isEmpty()) lines.add(i, "");
        return String.join("\n", lines) + "\n";
    }

    static List<Link> parseLinks(String md) {
        List<Link> out = new ArrayList<>();
        for (String line : splitLines(md == null ? "" : md)) {
            Matcher m = LINK_RE.matcher(line);
            if (m.find()) {
                String title = m.group(1).replace("\\[", "[").replace("\\]", "]");
                out.add(new Link(title, m.group(2) != null ? m.group(2) : m.group(3), line));
            }
        }
        return out;
    }

    static String removeLine(String md, String line) {
        List<String> lines = splitLines(md);
        if (!lines.remove(line)) return null;
        return String.join("\n", lines) + "\n";
    }

    // ------------------------------------------------------------- Tresor
    final GitHub gh;
    public final String folder;
    final String linksFile, notesDir, filesDir;

    public Tresor(GitHub gh, String folder) {
        this.gh = gh;
        this.folder = folder == null || folder.isEmpty() ? DEFAULT_FOLDER : folder;
        String base = folderDir(this.folder);
        linksFile = base + "/links.md";
        notesDir = base + "/notizen";
        filesDir = base + "/dateien";
    }

    String msg(String text) {
        return folder.equals(DEFAULT_FOLDER) ? text : text + " [" + folder + "]";
    }

    public List<String> listFolders() throws GitHub.GitHubError {
        List<String> names = new ArrayList<>();
        for (JSONObject e : gh.listDir(ROOT)) {
            String n = e.optString("name");
            if ("dir".equals(e.optString("type")) && !RESERVED.contains(n.toLowerCase(Locale.ROOT))) names.add(n);
        }
        Collections.sort(names, String.CASE_INSENSITIVE_ORDER);
        names.add(0, DEFAULT_FOLDER);
        return names;
    }

    public String createFolder(String name) throws GitHub.GitHubError {
        name = validateFolderName(name, listFolders());
        gh.putFile(folderDir(name) + "/" + KEEP_FILE, new byte[0], "Ordner erstellt: " + name, null);
        return name;
    }

    public String renameFolder(String oldName, String newName) throws GitHub.GitHubError {
        if (oldName.equals(DEFAULT_FOLDER))
            throw new IllegalArgumentException("„" + DEFAULT_FOLDER + "“ kann nicht umbenannt werden.");
        List<String> others = new ArrayList<>();
        for (String f : listFolders()) if (!f.equalsIgnoreCase(oldName)) others.add(f);
        newName = validateFolderName(newName, others);
        if (newName.equals(oldName)) return newName;
        gh.moveDir(folderDir(oldName), folderDir(newName), "Ordner umbenannt: " + oldName + " → " + newName);
        return newName;
    }

    public void deleteFolder(String name) throws GitHub.GitHubError {
        if (name.equals(DEFAULT_FOLDER))
            throw new IllegalArgumentException("„" + DEFAULT_FOLDER + "“ kann nicht gelöscht werden.");
        gh.deleteDir(folderDir(name), "Ordner gelöscht: " + name);
    }

    interface Change {
        String apply(String md);
    }

    /** links.md lesen, ändern, zurückschreiben – bei Konflikt kurz warten und erneut versuchen. */
    void updateLinks(Change change, String message) throws GitHub.GitHubError {
        int tries = 3;
        for (int attempt = 0; attempt < tries; attempt++) {
            boolean last = attempt == tries - 1;
            GitHub.FileData f = gh.getFile(linksFile);
            String newMd;
            try {
                newMd = change.apply(f == null ? "" : f.text());
            } catch (IllegalArgumentException e) {
                if (last) throw e;
                sleep();
                continue;
            }
            try {
                gh.putFile(linksFile, newMd.getBytes(StandardCharsets.UTF_8), msg(message), f == null ? null : f.sha);
                return;
            } catch (GitHub.GitHubError e) {
                if (last || !e.getMessage().contains("409")) throw e;
                sleep();
            }
        }
    }

    static void sleep() {
        try {
            Thread.sleep(1500);
        } catch (InterruptedException ignored) {
        }
    }

    public String addLink(String url, String title, String note) throws GitHub.GitHubError {
        url = normalizeUrl(url);
        if (url.isEmpty()) throw new IllegalArgumentException("Bitte einen Link eingeben.");
        String line = formatLinkLine(url, title, note);
        updateLinks(md -> insertLink(md, line), "Link: " + (title.trim().isEmpty() ? url : title.trim()));
        return url;
    }

    public String addNote(String title, String text) throws GitHub.GitHubError {
        if (title.trim().isEmpty() && text.trim().isEmpty()) throw new IllegalArgumentException("Die Notiz ist leer.");
        String stamp = new SimpleDateFormat("yyyy-MM-dd_HHmmss", Locale.GERMANY).format(new Date());
        String path = notesDir + "/" + stamp + "_" + slugify(title, "notiz") + ".md";
        String head = title.trim().isEmpty() ? "Notiz" : title.trim();
        String body = "# " + head + "\n\n_" + now() + "_\n\n" + text.trim() + "\n";
        gh.putFile(path, body.getBytes(StandardCharsets.UTF_8), msg("Notiz: " + head), null);
        return path;
    }

    String uniqueFilePath(String filename) throws GitHub.GitHubError {
        String name = safeFilename(filename);
        int dot = name.lastIndexOf('.');
        String base = dot > 0 ? name.substring(0, dot) : name, ext = dot > 0 ? name.substring(dot) : "";
        String path = filesDir + "/" + name;
        for (int n = 2; gh.exists(path); n++) path = filesDir + "/" + base + " (" + n + ")" + ext;
        return path;
    }

    public String addFile(String filename, byte[] data) throws GitHub.GitHubError {
        if (data.length > MAX_FILE_BYTES)
            throw new IllegalArgumentException(filename + " ist zu groß (" + data.length / (1024 * 1024) + " MB, max. 70 MB).");
        String path = uniqueFilePath(filename);
        gh.putFile(path, data, msg("Datei: " + path.substring(path.lastIndexOf('/') + 1)), null);
        return path;
    }

    public List<Link> recentLinks() throws GitHub.GitHubError {
        GitHub.FileData f = gh.getFile(linksFile);
        return parseLinks(f == null ? "" : f.text());
    }

    List<String> list(String dir, String suffix) throws GitHub.GitHubError {
        List<String> names = new ArrayList<>();
        for (JSONObject e : gh.listDir(dir)) {
            String n = e.optString("name");
            if ("file".equals(e.optString("type")) && !n.equals(KEEP_FILE) && n.endsWith(suffix)) names.add(n);
        }
        Collections.sort(names);
        if (!suffix.isEmpty()) Collections.reverse(names);
        return names;
    }

    /** Neueste zuerst. */
    public List<Entry> listNotes() throws GitHub.GitHubError {
        List<Entry> out = new ArrayList<>();
        for (String n : list(notesDir, ".md")) out.add(new Entry(noteLabel(n), notesDir + "/" + n));
        return out;
    }

    public List<Entry> listFiles() throws GitHub.GitHubError {
        List<Entry> out = new ArrayList<>();
        for (String n : list(filesDir, "")) out.add(new Entry(n, filesDir + "/" + n));
        return out;
    }

    public boolean isNote(String path) {
        return path.startsWith(notesDir + "/");
    }

    public void deleteLink(Link link) throws GitHub.GitHubError {
        updateLinks(md -> {
            String n = removeLine(md, link.line);
            if (n == null) throw new IllegalArgumentException("Der Link wurde schon gelöscht oder geändert.");
            return n;
        }, "Link gelöscht: " + link.title);
    }

    // ------------------------------------------------------- Bearbeiten
    /** Ändert einen Link an seiner Stelle (Datum bleibt). Gibt die neue Zeile zurück. */
    public String editLink(Link old, String url, String title, String note) throws GitHub.GitHubError {
        url = normalizeUrl(url);
        if (url.isEmpty()) throw new IllegalArgumentException("Bitte einen Link eingeben.");
        String[] parsed = parseLinkLine(old.line);
        String newLine = formatLinkLine(url, title, note, parsed == null ? null : parsed[3]);
        if (!newLine.equals(old.line)) {
            updateLinks(md -> {
                String n = replaceLine(md, old.line, newLine);
                if (n == null) throw new IllegalArgumentException("Der Link wurde inzwischen gelöscht oder geändert.");
                return n;
            }, "Link bearbeitet: " + (title.trim().isEmpty() ? url : title.trim()));
        }
        return newLine;
    }

    /** {titel, text} einer Notiz zum Bearbeiten. */
    public String[] readNoteParts(String path) throws GitHub.GitHubError {
        String[] p = parseNote(readNote(path));
        return new String[]{p[0], p[2]};
    }

    /** Ändert Titel/Text einer Notiz (Datum bleibt). Neuer Titel -> neuer Dateiname. Gibt den Pfad zurück. */
    public String editNote(String path, String title, String text) throws GitHub.GitHubError {
        if (title.trim().isEmpty() && text.trim().isEmpty()) throw new IllegalArgumentException("Die Notiz ist leer.");
        GitHub.FileData f = gh.getFile(path);
        if (f == null) throw new IllegalArgumentException("Die Notiz gibt es nicht mehr.");
        String stamp = parseNote(f.text())[1];
        String head = title.trim().isEmpty() ? "Notiz" : title.trim();
        byte[] body = ("# " + head + "\n\n_" + (stamp.isEmpty() ? now() : stamp) + "_\n\n" + text.trim() + "\n")
                .getBytes(StandardCharsets.UTF_8);
        String name = path.substring(path.lastIndexOf('/') + 1);
        Matcher m = Pattern.compile("^(\\d{4}-\\d{2}-\\d{2}_\\d{6})_").matcher(name);
        String newPath = m.find() ? notesDir + "/" + m.group(1) + "_" + slugify(title, "notiz") + ".md" : path;
        if (newPath.equals(path) || gh.exists(newPath)) {
            gh.putFile(path, body, msg("Notiz bearbeitet: " + head), f.sha);
            return path;
        }
        gh.putFile(newPath, body, msg("Notiz bearbeitet: " + head), null);
        gh.deleteFile(path, msg("Notiz umbenannt: " + name));
        return newPath;
    }

    /** Benennt eine Datei um (Endung bleibt, falls weggelassen). Gibt den neuen Pfad zurück. */
    public String renameFile(String path, String newName) throws GitHub.GitHubError {
        String oldName = path.substring(path.lastIndexOf('/') + 1);
        newName = safeFilename(newName.trim());
        int dot = oldName.lastIndexOf('.');
        if (newName.lastIndexOf('.') <= 0 && dot > 0) newName += oldName.substring(dot);
        if (newName.equals(oldName)) return path;
        GitHub.FileData f = gh.getFile(path);
        if (f == null) throw new IllegalArgumentException("Die Datei gibt es nicht mehr.");
        String newPath = uniqueFilePath(newName);
        gh.putFile(newPath, f.data, msg("Datei umbenannt: " + oldName + " → " + newPath.substring(newPath.lastIndexOf('/') + 1)), null);
        gh.deleteFile(path, msg("Datei umbenannt: " + oldName));
        return newPath;
    }

    public void deleteEntry(String path) throws GitHub.GitHubError {
        String kind = isNote(path) ? "Notiz" : "Datei";
        gh.deleteFile(path, msg(kind + " gelöscht: " + path.substring(path.lastIndexOf('/') + 1)));
    }

    public String readNote(String path) throws GitHub.GitHubError {
        GitHub.FileData f = gh.getFile(path);
        return f == null ? "" : f.text();
    }
}
