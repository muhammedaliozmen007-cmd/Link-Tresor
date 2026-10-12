package de.linktresor;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** TikTok-Videos herunterladen (Gegenstück zu app/tiktok.py – Download-Links über die TikWM-API). */
public class TikTok {
    public static String API = "https://www.tikwm.com/api/";
    static final String USER_AGENT = "Mozilla/5.0 (Linux; Android) Link-Tresor";
    static final long MIN_GAP_MS = 1200; // TikWM erlaubt ohne Konto etwa eine Anfrage pro Sekunde
    static long lastCall = 0;

    static final Pattern LINK_RE = Pattern.compile("https?://(?:[\\w-]+\\.)*(?:tiktok\\.com|tt\\.site)/[^\\s<>\"']+",
            Pattern.CASE_INSENSITIVE);
    static final Pattern ID_RE = Pattern.compile("(?<!\\d)\\d{18,20}(?!\\d)");

    public static class TikTokError extends Exception {
        public TikTokError(String msg) {
            super(msg);
        }
    }

    public interface Progress {
        void update(long done, long total);
    }

    public static class Info {
        public String id, user, title, date, video, music;
        public List<String> images = new ArrayList<>();
        public long size;

        /** Dateinamen: <user>_<datum>_<id>.mp4 bzw. …_1.jpg */
        public List<String> fileNames() {
            StringBuilder b = new StringBuilder(safeName(user));
            if (!date.isEmpty()) b.append('_').append(date);
            if (!id.isEmpty()) b.append('_').append(id);
            List<String> out = new ArrayList<>();
            if (video != null) out.add(b + ".mp4");
            else for (int i = 1; i <= images.size(); i++) out.add(b + "_" + i + ".jpg");
            return out;
        }

        public List<String> urls() {
            List<String> out = new ArrayList<>();
            if (video != null) out.add(video);
            else out.addAll(images);
            return out;
        }

        /** Dateiname für „Nur Ton“: <user>_<datum>_<id>.mp3 */
        public String mp3Name() {
            String first = fileNames().get(0);
            String base = video != null ? first.substring(0, first.lastIndexOf('.')) : first.substring(0, first.lastIndexOf('_'));
            return base + ".mp3";
        }

        public String link() {
            return "https://www.tiktok.com/@" + user + "/video/" + id;
        }
    }

    /** Alle TikTok-Links bzw. Video-IDs aus einem Text (ohne Doppelte). */
    public static List<String> findLinks(String text) {
        List<String> out = new ArrayList<>();
        if (text == null) return out;
        Matcher m = LINK_RE.matcher(text);
        while (m.find()) add(out, m.group());
        Matcher id = ID_RE.matcher(LINK_RE.matcher(text).replaceAll(" "));
        while (id.find()) add(out, id.group());
        return out;
    }

    static void add(List<String> out, String s) {
        s = s.replaceAll("[.,;)]+$", "");
        if (!out.contains(s)) out.add(s);
    }

    static String safeName(String text) {
        text = (text == null ? "" : text).replaceAll("[\\\\/:*?\"<>|\\x00-\\x1f]", "_").replaceAll("^[ ._]+|[ ._]+$", "");
        if (text.length() > 60) text = text.substring(0, 60);
        return text.isEmpty() ? "tiktok" : text;
    }

    static HttpURLConnection open(String url) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(30000);
        c.setReadTimeout(60000);
        c.setRequestProperty("User-Agent", USER_AGENT);
        return c;
    }

    static synchronized JSONObject api(String link) throws TikTokError {
        long wait = lastCall + MIN_GAP_MS - System.currentTimeMillis();
        if (wait > 0) {
            try {
                Thread.sleep(wait);
            } catch (InterruptedException ignored) {
            }
        }
        lastCall = System.currentTimeMillis();
        try {
            HttpURLConnection c = open(API + "?hd=1&url=" + URLEncoder.encode(link, "UTF-8"));
            int code = c.getResponseCode();
            if (code >= 400) throw new TikTokError("HTTP " + code + " vom Download-Dienst (TikWM)");
            String raw = new String(GitHub.readBytes(c.getInputStream()), StandardCharsets.UTF_8);
            c.disconnect();
            return new JSONObject(raw);
        } catch (TikTokError e) {
            throw e;
        } catch (IOException e) {
            throw new TikTokError("Keine Verbindung: " + e.getMessage());
        } catch (Exception e) {
            throw new TikTokError("Unerwartete Antwort vom Download-Dienst (TikWM).");
        }
    }

    /** Kurzlink (vm./vt.tiktok.com, tt.site) -> Ziel-URL. */
    static String resolve(String link) {
        try {
            HttpURLConnection c = open(link);
            c.setInstanceFollowRedirects(true);
            c.getResponseCode();
            String url = c.getURL().toString();
            c.disconnect();
            return url;
        } catch (IOException e) {
            return link;
        }
    }

    static String absolute(String url) {
        return url != null && url.startsWith("/") ? "https://www.tikwm.com" + url : url;
    }

    public static Info fetchInfo(String link) throws TikTokError {
        JSONObject r = api(link);
        String host = "";
        try {
            host = new URL(link).getHost();
        } catch (Exception ignored) {
        }
        if (r.optInt("code", -1) != 0 && !host.isEmpty() && !host.equals("www.tiktok.com") && !host.equals("tiktok.com")) {
            String fin = resolve(link);
            if (!fin.equals(link)) r = api(fin.split("\\?")[0]);
        }
        JSONObject d = r.optJSONObject("data");
        if (r.optInt("code", -1) != 0 || d == null) {
            String msg = r.optString("msg", "unbekannter Fehler");
            if (msg.toLowerCase(Locale.ROOT).contains("parsing")) msg = "Link nicht erkannt – ist das ein TikTok-Video?";
            throw new TikTokError(msg);
        }
        Info info = new Info();
        info.id = d.optString("id", "");
        JSONObject author = d.optJSONObject("author");
        info.user = author != null && !author.optString("unique_id").isEmpty() ? author.optString("unique_id") : "unbekannt";
        info.title = d.optString("title", "").trim();
        long created = d.optLong("create_time", 0);
        info.date = created > 0 ? new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).format(new Date(created * 1000)) : "";
        JSONArray imgs = d.optJSONArray("images");
        if (imgs != null && imgs.length() > 0) {
            for (int i = 0; i < imgs.length(); i++) info.images.add(absolute(imgs.optString(i)));
        } else {
            String hd = d.optString("hdplay", "");
            info.video = absolute(hd.isEmpty() ? d.optString("play", "") : hd);
        }
        info.size = d.optLong("hd_size", 0) > 0 ? d.optLong("hd_size") : d.optLong("size", 0);
        String music = d.optString("music", "");
        info.music = music.isEmpty() ? null : absolute(music);  // Ton des Beitrags als MP3
        return info;
    }

    /** Lädt url und schreibt sie nach out. */
    public static void download(String url, OutputStream out, Progress progress) throws TikTokError {
        try {
            HttpURLConnection c = open(url);
            int code = c.getResponseCode();
            if (code >= 400) throw new TikTokError("Download fehlgeschlagen: HTTP " + code);
            long total = c.getContentLengthLong(), done = 0;
            try (InputStream in = c.getInputStream()) {
                byte[] buf = new byte[256 * 1024];
                int n;
                while ((n = in.read(buf)) > 0) {
                    out.write(buf, 0, n);
                    done += n;
                    if (progress != null) progress.update(done, total);
                }
            }
            c.disconnect();
            if (done == 0) throw new TikTokError("Leere Datei erhalten.");
        } catch (IOException e) {
            throw new TikTokError("Keine Verbindung: " + e.getMessage());
        }
    }
}
