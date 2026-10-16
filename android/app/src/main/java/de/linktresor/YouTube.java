package de.linktresor;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * YouTube-Download am Handy (am PC macht das yt-dlp, das es für Android nicht gibt).
 * Fragt die Video-Infos wie die YouTube-App der Quest-Brille ab (Client „ANDROID_VR“) –
 * der liefert direkte Download-Adressen ohne JavaScript-Entschlüsselung.
 * Video und Ton kommen getrennt; MainActivity fügt sie mit MediaMuxer zu einer MP4 zusammen.
 */
public class YouTube {
    public static String API = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false";
    static final String CLIENT_NAME = "ANDROID_VR", CLIENT_ID = "28", CLIENT_VERSION = "1.65.10";
    static final String USER_AGENT = "com.google.android.apps.youtube.vr.oculus/" + CLIENT_VERSION
            + " (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip";
    static final long CHUNK = 10L * 1024 * 1024; // in Stücken laden, sonst bremst YouTube stark

    static final Pattern LINK_RE = Pattern.compile(
            "(?:https?://)?(?:[\\w-]+\\.)*(?:youtube\\.com|youtube-nocookie\\.com|youtu\\.be)/[^\\s<>\"']+",
            Pattern.CASE_INSENSITIVE);
    static final Pattern ID_IN_LINK = Pattern.compile(
            "(?:[?&]v=|youtu\\.be/|/shorts/|/live/|/embed/|/v/)([\\w-]{11})(?![\\w-])");

    public static class YouTubeError extends Exception {
        public YouTubeError(String msg) {
            super(msg);
        }
    }

    public interface Progress {
        void update(long done, long total);
    }

    public static class Stream {
        public String url, mime, codecs, quality;
        public int itag, height;
        public long bitrate, size;

        boolean isVideo() {
            return mime.startsWith("video/");
        }
    }

    public static class Info {
        public String id, title, author;
        public long seconds;
        public List<Stream> muxed = new ArrayList<>(), adaptive = new ArrayList<>();

        public String link() {
            return "https://www.youtube.com/watch?v=" + id;
        }

        /** Dateiname ohne Endung: „Titel“ (wie am PC, ohne verbotene Zeichen). */
        public String baseName() {
            return safeName(title.isEmpty() ? id : title);
        }
    }

    /** Was geladen werden soll: Video (mit Ton, ggf. zusammenzufügen) oder nur Ton. */
    public static class Plan {
        public Stream video, audio, muxed;  // entweder muxed oder video+audio, bei „Nur Ton“ nur audio
        public String ext;

        public long size() {
            long s = 0;
            for (Stream x : new Stream[]{video, audio, muxed}) if (x != null) s += x.size;
            return s;
        }
    }

    /** Video-IDs aus einem Text (ohne Doppelte, Reihenfolge bleibt). */
    public static List<String> findIds(String text) {
        List<String> out = new ArrayList<>();
        if (text == null) return out;
        Matcher m = LINK_RE.matcher(text);
        while (m.find()) {
            Matcher id = ID_IN_LINK.matcher(m.group());
            if (id.find() && !out.contains(id.group(1))) out.add(id.group(1));
        }
        return out;
    }

    /** Nur Playlist/Kanal-Links ohne einzelnes Video (gehen am Handy nicht). */
    public static boolean hasListOnly(String text) {
        Matcher m = LINK_RE.matcher(text == null ? "" : text);
        while (m.find()) if (!ID_IN_LINK.matcher(m.group()).find()) return true;
        return false;
    }

    static String safeName(String text) {
        text = (text == null ? "" : text).replaceAll("[\\\\/:*?\"<>|\\x00-\\x1f]", "_").replaceAll("\\s+", " ")
                .replaceAll("^[ ._]+|[ ._]+$", "");
        if (text.length() > 80) text = text.substring(0, 80).trim();
        return text.isEmpty() ? "youtube" : text;
    }

    static HttpURLConnection open(String url) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(30000);
        c.setReadTimeout(60000);
        c.setRequestProperty("User-Agent", USER_AGENT);
        return c;
    }

    public static Info fetchInfo(String id) throws YouTubeError {
        JSONObject r;
        try {
            JSONObject client = new JSONObject()
                    .put("clientName", CLIENT_NAME).put("clientVersion", CLIENT_VERSION)
                    .put("deviceMake", "Oculus").put("deviceModel", "Quest 3")
                    .put("androidSdkVersion", 32).put("osName", "Android").put("osVersion", "12L")
                    .put("hl", "de").put("gl", "DE");
            JSONObject body = new JSONObject().put("videoId", id)
                    .put("context", new JSONObject().put("client", client))
                    .put("contentCheckOk", true).put("racyCheckOk", true);
            HttpURLConnection c = open(API);
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            c.setRequestProperty("X-YouTube-Client-Name", CLIENT_ID);
            c.setRequestProperty("X-YouTube-Client-Version", CLIENT_VERSION);
            try (OutputStream o = c.getOutputStream()) {
                o.write(body.toString().getBytes(StandardCharsets.UTF_8));
            }
            int code = c.getResponseCode();
            if (code >= 400) throw new YouTubeError("HTTP " + code + " von YouTube");
            r = new JSONObject(new String(GitHub.readBytes(c.getInputStream()), StandardCharsets.UTF_8));
            c.disconnect();
        } catch (YouTubeError e) {
            throw e;
        } catch (IOException e) {
            throw new YouTubeError("Keine Verbindung: " + e.getMessage());
        } catch (Exception e) {
            throw new YouTubeError("Unerwartete Antwort von YouTube.");
        }
        return parse(id, r);
    }

    static Info parse(String id, JSONObject r) throws YouTubeError {
        JSONObject ps = r.optJSONObject("playabilityStatus");
        String status = ps == null ? "" : ps.optString("status");
        if (!"OK".equals(status)) {
            String why = ps == null ? "" : ps.optString("reason", "");
            if ("LOGIN_REQUIRED".equals(status) && why.toLowerCase(Locale.ROOT).contains("bot"))
                why = "YouTube will eine Anmeldung („kein Bot“) – bitte später nochmal oder am PC laden";
            else if ("LOGIN_REQUIRED".equals(status))
                why = "nur mit Anmeldung sichtbar (z. B. Altersgrenze oder privat) – bitte am PC laden";
            throw new YouTubeError(why.isEmpty() ? "Video nicht verfügbar (" + status + ")" : why);
        }
        JSONObject vd = r.optJSONObject("videoDetails");
        Info info = new Info();
        info.id = id;
        info.title = vd == null ? "" : vd.optString("title", "").trim();
        info.author = vd == null ? "" : vd.optString("author", "").trim();
        info.seconds = vd == null ? 0 : vd.optLong("lengthSeconds", 0);
        if (vd != null && vd.optBoolean("isLive", false))
            throw new YouTubeError("Live-Übertragungen gehen am Handy nicht.");
        JSONObject sd = r.optJSONObject("streamingData");
        if (sd != null) {
            addStreams(sd.optJSONArray("formats"), info.muxed, info.seconds);
            addStreams(sd.optJSONArray("adaptiveFormats"), info.adaptive, info.seconds);
        }
        if (info.muxed.isEmpty() && info.adaptive.isEmpty())
            throw new YouTubeError("YouTube liefert für dieses Video keine Download-Adresse – bitte am PC laden.");
        return info;
    }

    static void addStreams(JSONArray arr, List<Stream> out, long seconds) {
        if (arr == null) return;
        for (int i = 0; i < arr.length(); i++) {
            JSONObject f = arr.optJSONObject(i);
            if (f == null || f.optString("url").isEmpty()) continue;  // verschlüsselte Adressen können wir nicht
            Stream s = new Stream();
            s.url = f.optString("url");
            String mt = f.optString("mimeType", "");
            int semi = mt.indexOf(';');
            s.mime = (semi < 0 ? mt : mt.substring(0, semi)).trim();
            Matcher cm = Pattern.compile("codecs=\"([^\"]*)\"").matcher(mt);
            s.codecs = cm.find() ? cm.group(1) : "";
            s.itag = f.optInt("itag");
            s.height = f.optInt("height");
            s.quality = f.optString("qualityLabel", "");
            s.bitrate = f.optLong("bitrate", 0);
            s.size = f.optLong("contentLength", 0);
            if (s.size == 0 && seconds > 0) s.size = s.bitrate * seconds / 8;  // grob geschätzt
            out.add(s);
        }
    }

    /**
     * Beste passende Auswahl: maxHeight 0 = beste Qualität; audioOnly = nur Ton (M4A).
     * Zum Zusammenfügen nur H.264 + AAC, das kann Androids MediaMuxer sicher.
     */
    public static Plan choose(Info info, int maxHeight, boolean audioOnly) throws YouTubeError {
        Plan p = new Plan();
        for (Stream s : info.adaptive)
            if (s.mime.equals("audio/mp4") && s.codecs.startsWith("mp4a") && (p.audio == null || s.bitrate > p.audio.bitrate))
                p.audio = s;
        if (audioOnly) {
            if (p.audio == null) throw new YouTubeError("Keine Tonspur gefunden.");
            p.ext = "m4a";
            return p;
        }
        for (Stream s : info.adaptive)
            if (s.mime.equals("video/mp4") && s.codecs.startsWith("avc1")
                    && (maxHeight == 0 || s.height <= maxHeight)
                    && (p.video == null || s.height > p.video.height
                    || (s.height == p.video.height && s.bitrate > p.video.bitrate)))
                p.video = s;
        Stream best = null;
        for (Stream s : info.muxed)
            if (s.mime.equals("video/mp4") && (maxHeight == 0 || s.height <= maxHeight)
                    && (best == null || s.height > best.height))
                best = s;
        p.ext = "mp4";
        if (p.video != null && p.audio != null && (best == null || p.video.height > best.height)) return p;
        if (best == null) throw new YouTubeError("Kein passendes Video-Format gefunden – bitte am PC laden.");
        p.video = p.audio = null;
        p.muxed = best;
        return p;
    }

    /** Lädt einen Stream in Stücken (range=…) nach out. */
    public static void download(Stream s, OutputStream out, Progress progress) throws YouTubeError {
        long done = 0, total = s.size;
        byte[] buf = new byte[256 * 1024];
        try {
            while (true) {
                long end = done + CHUNK - 1;
                HttpURLConnection c = open(s.url + (s.url.contains("?") ? "&" : "?") + "range=" + done + "-" + end);
                int code = c.getResponseCode();
                if (code == 416) {  // über das Ende hinaus -> fertig
                    c.disconnect();
                    break;
                }
                if (code >= 400) throw new YouTubeError("Download fehlgeschlagen: HTTP " + code);
                long got = 0;
                try (InputStream in = c.getInputStream()) {
                    int n;
                    while ((n = in.read(buf)) > 0) {
                        out.write(buf, 0, n);
                        got += n;
                        done += n;
                        if (progress != null) progress.update(done, Math.max(total, done));
                    }
                }
                c.disconnect();
                if (got < CHUNK || (total > 0 && done >= total)) break;
            }
        } catch (IOException e) {
            throw new YouTubeError("Keine Verbindung: " + e.getMessage());
        }
        if (done == 0) throw new YouTubeError("Leere Datei erhalten.");
    }
}
