package de.linktresor;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.provider.Settings;
import android.text.InputType;
import android.text.method.LinkMovementMethod;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.webkit.MimeTypeMap;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.PopupMenu;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MainActivity extends Activity {
    // Daten (Tresor, Feedback, Klingel) im privaten Repo, App-Updates aus dem öffentlichen
    static final String DEFAULT_REPO = "muhammedaliozmen007-cmd/Link-Tresor-Privat";
    static final String APP_REPO = "muhammedaliozmen007-cmd/Link-Tresor";
    static final String DEFAULT_BRANCH = "main";
    static final String TOKEN_URL = "https://github.com/settings/tokens/new?scopes=repo&description=Link-Tresor-Handy";
    static final String RELEASE_TAG = "android";
    static final String APK_NAME = "Link-Tresor.apk";

    // Farben wie in der Windows-App (Dark Mode)
    static final int BG = 0xFF1E1F22, CARD = 0xFF2B2D31, FIELD = 0xFF383A40, LINE = 0xFF4E5058;
    static final int TEXT = 0xFFE6E6E6, MUTED = 0xFF9AA0A6, ACCENT = 0xFF3B82F6, DANGER = 0xFFE5534B;

    static final int PICK_FILES = 1, ASK_STORAGE = 2;

    final ExecutorService worker = Executors.newSingleThreadExecutor();
    final Handler ui = new Handler(Looper.getMainLooper());
    SharedPreferences prefs;

    String folder = Tresor.DEFAULT_FOLDER;
    List<String> folders = new ArrayList<>();
    // Klingel: offene Feedbacks {nr, titel, gerufen "1"/"0"} + lokal Bekanntes, das GitHub evtl. noch nicht liefert
    List<String[]> feedbackItems = new ArrayList<>();
    final java.util.Map<String, Long> freshRung = new java.util.HashMap<>();
    final java.util.Map<String, String[]> freshFeedback = new java.util.HashMap<>();
    static final long FRESH_MS = 120_000, BELL_REFRESH_MS = 60_000;
    final Runnable bellTimer = new Runnable() {
        @Override
        public void run() {
            refreshBell();
            ui.postDelayed(this, BELL_REFRESH_MS);
        }
    };

    Spinner folderBox;
    Button bellButton;
    ArrayAdapter<String> folderAdapter;
    boolean folderBoxUpdating;
    static final int TAB_LINK = 0, TAB_NOTE = 1, TAB_FILE = 2, TAB_TIKTOK = 3, TAB_OVERVIEW = 4;
    final Button[] tabButtons = new Button[5];
    final View[] tabViews = new View[5];
    int currentTab = 0;
    TextView status;
    EditText linkUrl, linkTitle, linkNote, noteTitle, noteText;
    TextView fileInfo, ttLog;
    EditText ttLinks;
    RadioButton ttToPhone, ttToTresor, ttAsVideo, ttAsMp3;
    android.widget.CheckBox ttKeepLink;
    Button ttButton;
    ListView overview;
    final List<Object> overviewItems = new ArrayList<>();  // angezeigt (gefiltert)
    final List<Object> overviewAll = new ArrayList<>();    // alles im Ordner
    EditText searchBox;
    boolean updateAvailable;
    java.util.Map<String, String> rungOpen;  // gerufene, noch offene Feedbacks (nr -> titel)
    ArrayAdapter<Object> overviewAdapter;

    // ================================================================= Start
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("tresor", MODE_PRIVATE);
        // Früher lag alles im (jetzt öffentlichen) App-Repo -> Daten-Repo umstellen
        if (prefs.getString("repo", "").trim().equalsIgnoreCase(APP_REPO))
            prefs.edit().putString("repo", DEFAULT_REPO).apply();
        folder = prefs.getString("folder", Tresor.DEFAULT_FOLDER);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        setContentView(buildUi());
        setupActionBar();
        selectTab(0);
        cleanupOldDownloads();

        if (prefs.getString("token", "").isEmpty()) {
            setStatus("Willkommen! Bitte zuerst Token eintragen.");
            openSettings();
        } else {
            loadFolders(null);
            refreshBell();
            checkUpdateQuietly();
        }
        handleShare(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        handleShare(intent);
    }

    @Override
    protected void onResume() {
        super.onResume();
        ui.postDelayed(bellTimer, BELL_REFRESH_MS);
    }

    @Override
    protected void onPause() {
        ui.removeCallbacks(bellTimer);
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        worker.shutdownNow();
        super.onDestroy();
    }

    static String version() {
        String sha = BuildConfig.BUILD_SHA;
        return "dev".equals(sha) ? "dev" : sha.substring(0, Math.min(7, sha.length()));
    }

    // ================================================================= Menü
    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, 2, 1, "💡 Feedback");
        menu.add(0, 3, 2, "🌐 GitHub");
        menu.add(0, 4, 3, updateAvailable ? "⬆ Update verfügbar!" : "⬆ Update");
        // Zahnrad direkt in der Leiste (neben ⋮), nicht im Menü versteckt
        menu.add(0, 5, 0, "Einstellungen").setIcon(R.drawable.ic_settings)
                .setShowAsAction(MenuItem.SHOW_AS_ACTION_ALWAYS);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        switch (item.getItemId()) {
            case 2: openFeedbackDialog(); return true;
            case 3: openUrl("https://github.com/" + prefs.getString("repo", DEFAULT_REPO)); return true;
            case 4: checkUpdate(); return true;
            case 5: openSettings(); return true;
        }
        return super.onOptionsItemSelected(item);
    }

    // ============================================================ Oberfläche
    int dp(float v) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics()));
    }

    GradientDrawable box(int color, int stroke) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(color);
        d.setCornerRadius(dp(8));
        if (stroke != 0) d.setStroke(dp(1), stroke);
        return d;
    }

    TextView label(String text) {
        TextView t = new TextView(this);
        t.setText(text);
        t.setTextColor(TEXT);
        t.setTextSize(14);
        t.setPadding(0, dp(10), 0, dp(4));
        return t;
    }

    EditText field(String hint, boolean multi) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setTextColor(TEXT);
        e.setHintTextColor(MUTED);
        e.setTextSize(16);
        e.setBackground(box(FIELD, LINE));
        e.setPadding(dp(12), dp(10), dp(12), dp(10));
        if (multi) {
            e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE
                    | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
            e.setGravity(Gravity.TOP | Gravity.START);
            e.setMinLines(6);
        } else {
            e.setSingleLine(true);
        }
        return e;
    }

    Button button(String text, int color, View.OnClickListener click) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextColor(Color.WHITE);
        b.setTextSize(15);
        b.setBackground(box(color, color == CARD ? LINE : 0));
        b.setPadding(dp(14), 0, dp(14), 0);
        b.setMinHeight(dp(46));
        b.setMinimumHeight(dp(46));
        b.setStateListAnimator(null);
        b.setOnClickListener(click);
        return b;
    }

    LinearLayout row() {
        LinearLayout r = new LinearLayout(this);
        r.setOrientation(LinearLayout.HORIZONTAL);
        r.setGravity(Gravity.CENTER_VERTICAL);
        return r;
    }

    static LinearLayout.LayoutParams weight(float w) {
        return new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, w);
    }

    LinearLayout.LayoutParams margins(int l, int t, int r, int b) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        p.setMargins(dp(l), dp(t), dp(r), dp(b));
        return p;
    }

    View buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);
        root.setPadding(dp(12), dp(10), dp(12), dp(6));

        // --- Ordner-Leiste
        LinearLayout bar = row();
        TextView fl = new TextView(this);
        fl.setText("📁");
        fl.setTextSize(20);
        fl.setPadding(0, 0, dp(8), 0);
        bar.addView(fl);
        folderBox = new Spinner(this, Spinner.MODE_DROPDOWN);
        folderBox.setBackground(box(FIELD, LINE));
        folderBox.setPopupBackgroundDrawable(box(CARD, LINE));
        folderAdapter = new ArrayAdapter<String>(this, android.R.layout.simple_spinner_item, folders) {
            @Override
            public View getView(int pos, View convert, ViewGroup parent) {
                return styleRow(super.getView(pos, convert, parent), false);
            }

            @Override
            public View getDropDownView(int pos, View convert, ViewGroup parent) {
                return styleRow(super.getDropDownView(pos, convert, parent), true);
            }
        };
        folders.add(folder);
        folderBox.setAdapter(folderAdapter);
        folderBox.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> p, View v, int pos, long id) {
                if (folderBoxUpdating || pos >= folders.size()) return;
                String f = folders.get(pos);
                if (!f.equals(folder)) switchFolder(f);
            }

            @Override
            public void onNothingSelected(AdapterView<?> p) {
            }
        });
        bar.addView(folderBox, weight(1));
        Button add = button("＋ Neu", CARD, v -> newFolder());
        LinearLayout.LayoutParams ap = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(46));
        ap.setMargins(dp(8), 0, 0, 0);
        bar.addView(add, ap);
        Button more = button("⋮", CARD, this::folderMenu);
        LinearLayout.LayoutParams mp = new LinearLayout.LayoutParams(dp(46), dp(46));
        mp.setMargins(dp(6), 0, 0, 0);
        bar.addView(more, mp);
        root.addView(bar);

        // --- Tabs
        LinearLayout tabs = row();
        String[] names = {"🔗\nLink", "📝\nNotiz", "📎\nDatei", "🎵\nTikTok", "📋\nÜbersicht"};
        for (int i = 0; i < names.length; i++) {
            final int idx = i;
            Button b = button(names[i], CARD, v -> selectTab(idx));
            b.setTextSize(12);
            b.setLineSpacing(0, 0.9f);
            b.setPadding(dp(2), dp(4), dp(2), dp(4));
            b.setMinHeight(dp(54));
            b.setMinimumHeight(dp(54));
            LinearLayout.LayoutParams p = weight(1);
            p.setMargins(i == 0 ? 0 : dp(4), 0, 0, 0);
            tabs.addView(b, p);
            tabButtons[i] = b;
        }
        root.addView(tabs, margins(0, 12, 0, 8));

        // --- Inhalt
        FrameLayout content = new FrameLayout(this);
        tabViews[0] = buildLinkTab();
        tabViews[1] = buildNoteTab();
        tabViews[2] = buildFileTab();
        tabViews[3] = buildTikTokTab();
        tabViews[4] = buildOverviewTab();
        for (View v : tabViews) content.addView(v);
        root.addView(content, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));

        status = new TextView(this);
        status.setTextColor(MUTED);
        status.setTextSize(13);
        status.setText("Bereit.");
        status.setPadding(dp(2), dp(6), dp(2), 0);
        root.addView(status);
        return root;
    }

    View styleRow(View v, boolean dropDown) {
        if (v instanceof TextView) {
            TextView t = (TextView) v;
            t.setTextColor(TEXT);
            t.setTextSize(16);
            t.setPadding(dp(12), dp(dropDown ? 12 : 8), dp(12), dp(dropDown ? 12 : 8));
        }
        return v;
    }

    /** Senkrechte Spalte – Ausrichtung VOR dem Befüllen setzen, sonst werden Felder nur so breit wie ihr Inhalt. */
    LinearLayout column() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        return l;
    }

    ScrollView card(LinearLayout inner) {
        inner.setPadding(dp(14), dp(4), dp(14), dp(14));
        ScrollView s = new ScrollView(this);
        s.setBackground(box(CARD, 0));
        s.setFillViewport(true);
        s.addView(inner);
        return s;
    }

    View buildLinkTab() {
        LinearLayout l = column();
        l.addView(label("Link (URL):"));
        linkUrl = field("https://…", false);
        linkUrl.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        l.addView(linkUrl);
        l.addView(label("Titel (optional):"));
        linkTitle = field("", false);
        l.addView(linkTitle);
        l.addView(label("Notiz (optional):"));
        linkNote = field("", false);
        l.addView(linkNote);
        LinearLayout r = row();
        r.addView(button("📋 Einfügen", CARD, v -> pasteLink()), weight(1));
        Button save = button("Im Tresor speichern", ACCENT, v -> saveLink());
        LinearLayout.LayoutParams p = weight(1.4f);
        p.setMargins(dp(8), 0, 0, 0);
        r.addView(save, p);
        l.addView(r, margins(0, 16, 0, 0));
        return card(l);
    }

    View buildNoteTab() {
        LinearLayout l = column();
        l.addView(label("Titel:"));
        noteTitle = field("", false);
        noteTitle.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        l.addView(noteTitle);
        l.addView(label("Text:"));
        noteText = field("", true);
        noteText.setMinLines(8);
        l.addView(noteText);
        l.addView(button("Notiz speichern", ACCENT, v -> saveNote()), margins(0, 16, 0, 0));
        return card(l);
    }

    View buildFileTab() {
        LinearLayout l = column();
        TextView t = label("Dateien vom Handy (Fotos, PDFs, …) in den Tresor hochladen – max. 70 MB pro Datei. "
                + "Tipp: Du kannst auch in jeder App auf „Teilen“ → Link-Tresor tippen.");
        t.setTextColor(MUTED);
        l.addView(t);
        l.addView(button("📂 Dateien auswählen …", ACCENT, v -> pickFiles()), margins(0, 12, 0, 0));
        fileInfo = new TextView(this);
        fileInfo.setTextColor(TEXT);
        fileInfo.setPadding(0, dp(12), 0, 0);
        l.addView(fileInfo);
        return card(l);
    }

    View buildTikTokTab() {
        LinearLayout l = column();
        l.addView(label("TikTok-Links (einer pro Zeile – auch mehrere):"));
        ttLinks = field("https://www.tiktok.com/@…/video/…", true);
        ttLinks.setMinLines(3);
        ttLinks.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE | InputType.TYPE_TEXT_VARIATION_URI);
        l.addView(ttLinks);

        l.addView(label("Als:"));
        RadioGroup kind = new RadioGroup(this);
        kind.setOrientation(RadioGroup.HORIZONTAL);
        ttAsVideo = new RadioButton(this);
        ttAsMp3 = new RadioButton(this);
        ttAsVideo.setText("🎬 Video");
        ttAsMp3.setText("🎵 Nur Ton (MP3)");
        for (RadioButton r : new RadioButton[]{ttAsVideo, ttAsMp3}) {
            r.setTextColor(TEXT);
            r.setTextSize(15);
            r.setId(View.generateViewId());
            r.setPadding(0, 0, dp(16), 0);
            kind.addView(r);
        }
        (prefs.getString("tiktok_kind", "video").equals("mp3") ? ttAsMp3 : ttAsVideo).setChecked(true);
        kind.setOnCheckedChangeListener((g, id) ->
                prefs.edit().putString("tiktok_kind", ttAsMp3.isChecked() ? "mp3" : "video").apply());
        l.addView(kind);

        l.addView(label("Speichern:"));
        RadioGroup where = new RadioGroup(this);
        ttToPhone = new RadioButton(this);
        ttToTresor = new RadioButton(this);
        ttToPhone.setText("📱 Aufs Handy (Download/TikTok)");
        ttToTresor.setText("🔒 In den Tresor (aktueller Ordner)");
        for (RadioButton r : new RadioButton[]{ttToPhone, ttToTresor}) {
            r.setTextColor(TEXT);
            r.setTextSize(15);
            r.setId(View.generateViewId());
            where.addView(r);
        }
        (prefs.getString("tiktok_target", "phone").equals("tresor") ? ttToTresor : ttToPhone).setChecked(true);
        where.setOnCheckedChangeListener((g, id) ->
                prefs.edit().putString("tiktok_target", ttToTresor.isChecked() ? "tresor" : "phone").apply());
        l.addView(where);
        ttKeepLink = new android.widget.CheckBox(this);
        ttKeepLink.setText("Link zusätzlich im Tresor merken");
        ttKeepLink.setTextColor(TEXT);
        ttKeepLink.setTextSize(15);
        ttKeepLink.setChecked(prefs.getBoolean("tiktok_link", true));
        ttKeepLink.setOnCheckedChangeListener((b, on) -> prefs.edit().putBoolean("tiktok_link", on).apply());
        l.addView(ttKeepLink);

        LinearLayout r = row();
        r.addView(button("📋 Einfügen", CARD, v -> pasteTikTok()), weight(1));
        ttButton = button("⬇ Herunterladen", ACCENT, v -> downloadTikTok());
        LinearLayout.LayoutParams p = weight(1.4f);
        p.setMargins(dp(8), 0, 0, 0);
        r.addView(ttButton, p);
        l.addView(r, margins(0, 12, 0, 0));

        ttLog = new TextView(this);
        ttLog.setTextColor(TEXT);
        ttLog.setTextSize(13);
        ttLog.setTextIsSelectable(true);
        ttLog.setPadding(0, dp(12), 0, 0);
        l.addView(ttLog);
        return card(l);
    }

    View buildOverviewTab() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setBackground(box(CARD, 0));
        l.setPadding(dp(6), dp(6), dp(6), dp(6));
        searchBox = field("🔍 Suchen …", false);
        searchBox.addTextChangedListener(new android.text.TextWatcher() {
            public void beforeTextChanged(CharSequence c, int a, int b, int d) {
            }

            public void onTextChanged(CharSequence c, int a, int b, int d) {
            }

            public void afterTextChanged(android.text.Editable e) {
                applyFilter();
            }
        });
        l.addView(searchBox, margins(0, 0, 0, 6));
        overview = new ListView(this);
        overview.setDivider(null);
        overviewAdapter = new ArrayAdapter<Object>(this, android.R.layout.simple_list_item_1, overviewItems) {
            @Override
            public boolean isEnabled(int pos) {
                return !(getItem(pos) instanceof String);
            }

            @Override
            public View getView(int pos, View convert, ViewGroup parent) {
                TextView t = (TextView) super.getView(pos, convert, parent);
                Object o = getItem(pos);
                t.setTextColor(o instanceof String ? MUTED : TEXT);
                t.setTypeface(null, o instanceof String ? Typeface.BOLD : Typeface.NORMAL);
                t.setTextSize(o instanceof String ? 13 : 15);
                t.setMinHeight(dp(o instanceof String ? 34 : 44));
                t.setPadding(dp(10), dp(o instanceof String ? 10 : 4), dp(10), dp(4));
                if (o instanceof Tresor.Link) t.setText("🔗  " + ((Tresor.Link) o).title);
                else if (o instanceof Tresor.Entry) {
                    Tresor.Entry e = (Tresor.Entry) o;
                    t.setText((tresor().isNote(e.path) ? "📝  " : "📎  ") + e.label);
                } else t.setText(String.valueOf(o));
                return t;
            }
        };
        overview.setAdapter(overviewAdapter);
        overview.setOnItemClickListener((p, v, pos, id) -> openEntry(overviewItems.get(pos)));
        overview.setOnItemLongClickListener((p, v, pos, id) -> {
            entryMenu(overviewItems.get(pos));
            return true;
        });
        l.addView(overview, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        TextView hint = new TextView(this);
        hint.setText("Antippen = öffnen · lange drücken = bearbeiten / löschen");
        hint.setTextColor(MUTED);
        hint.setTextSize(12);
        hint.setPadding(dp(10), dp(4), dp(10), dp(4));
        l.addView(hint);
        LinearLayout r = row();
        r.addView(button("⟳ Aktualisieren", FIELD, v -> loadOverview()), weight(1));
        Button gh = button("Auf GitHub ↗", FIELD, v -> openUrl(client().treeUrl(Tresor.folderDir(folder))));
        LinearLayout.LayoutParams p = weight(1);
        p.setMargins(dp(6), 0, 0, 0);
        r.addView(gh, p);
        l.addView(r);
        return l;
    }

    void selectTab(int idx) {
        currentTab = idx;
        for (int i = 0; i < tabViews.length; i++) {
            tabViews[i].setVisibility(i == idx ? View.VISIBLE : View.GONE);
            tabButtons[i].setBackground(box(i == idx ? ACCENT : CARD, i == idx ? 0 : LINE));
        }
        hideKeyboard();
        if (idx == TAB_OVERVIEW && hasToken()) loadOverview();
    }

    void hideKeyboard() {
        View f = getCurrentFocus();
        if (f != null)
            ((InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(f.getWindowToken(), 0);
    }

    // ============================================================ Hintergrund
    interface Job<T> {
        T run() throws Exception;
    }

    interface Done<T> {
        void done(T result);
    }

    <T> void runJob(String what, Job<T> job, Done<T> done) {
        runJob(what, job, done, null);
    }

    <T> void runJob(String what, Job<T> job, Done<T> done, Done<Exception> failed) {
        if (what != null) setStatus(what + " …");
        worker.execute(() -> {
            try {
                T result = job.run();
                ui.post(() -> {
                    if (isFinishing()) return;
                    if (what != null && status.getText().toString().equals(what + " …")) setStatus("Bereit.");
                    if (done != null) done.done(result);
                });
            } catch (Exception e) {
                ui.post(() -> {
                    if (isFinishing()) return;
                    if (failed != null) {
                        setStatus("Bereit.");
                        failed.done(e);
                    } else {
                        setStatus("✖ " + e.getMessage());
                        alert("Fehler", e.getMessage());
                    }
                });
            }
        });
    }

    void setStatus(String text) {
        status.setText(text);
    }

    void alert(String title, String text) {
        new AlertDialog.Builder(this).setTitle(title).setMessage(text).setPositiveButton("OK", null).show();
    }

    void confirm(String title, String text, String yes, Runnable action) {
        new AlertDialog.Builder(this).setTitle(title).setMessage(text)
                .setPositiveButton(yes, (d, w) -> action.run()).setNegativeButton("Abbrechen", null).show();
    }

    boolean hasToken() {
        return !prefs.getString("token", "").isEmpty();
    }

    GitHub client() {
        return new GitHub(prefs.getString("token", ""), prefs.getString("repo", DEFAULT_REPO),
                prefs.getString("branch", DEFAULT_BRANCH));
    }

    Tresor tresor() {
        return new Tresor(client(), folder);
    }

    boolean needToken() {
        if (hasToken()) return false;
        alert("Link-Tresor", "Bitte zuerst in den Einstellungen einen Token eintragen.");
        openSettings();
        return true;
    }

    void openUrl(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception e) {
            alert("Link-Tresor", "Kein Programm zum Öffnen gefunden:\n" + url);
        }
    }

    // ================================================================ Ordner
    void loadFolders(String select) {
        if (!hasToken()) return;
        runJob("Lade Ordner", () -> tresor().listFolders(), list -> {
            folders.clear();
            folders.addAll(list);
            String want = select != null ? select : folder;
            if (!folders.contains(want)) want = Tresor.DEFAULT_FOLDER;
            folder = want;
            prefs.edit().putString("folder", folder).apply();
            folderBoxUpdating = true;
            folderAdapter.notifyDataSetChanged();
            folderBox.setSelection(folders.indexOf(folder));
            folderBox.post(() -> folderBoxUpdating = false);
            if (currentTab == TAB_OVERVIEW) loadOverview();
        });
    }

    void switchFolder(String f) {
        folder = f;
        prefs.edit().putString("folder", f).apply();
        setStatus("Ordner: " + f);
        if (currentTab == TAB_OVERVIEW) loadOverview();
    }

    void askName(String title, String preset, Done<String> done) {
        EditText e = field("Name", false);
        e.setText(preset);
        e.setSelection(preset.length());
        FrameLayout f = new FrameLayout(this);
        f.setPadding(dp(20), dp(10), dp(20), 0);
        f.addView(e);
        AlertDialog d = new AlertDialog.Builder(this).setTitle(title).setView(f)
                .setPositiveButton("OK", (x, w) -> done.done(e.getText().toString()))
                .setNegativeButton("Abbrechen", null).create();
        d.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_VISIBLE);
        d.show();
    }

    void newFolder() {
        if (needToken()) return;
        askName("Neuer Ordner", "", name -> runJob("Erstelle Ordner", () -> tresor().createFolder(name), created -> {
            setStatus("✔ Ordner „" + created + "“ erstellt.");
            loadFolders(created);
        }));
    }

    void folderMenu(View anchor) {
        PopupMenu m = new PopupMenu(this, anchor);
        m.getMenu().add(0, 1, 0, "✎ Umbenennen");
        m.getMenu().add(0, 2, 1, "🗑 Ordner löschen");
        m.setOnMenuItemClickListener(item -> {
            if (needToken()) return true;
            if (folder.equals(Tresor.DEFAULT_FOLDER)) {
                alert("Link-Tresor", "„" + Tresor.DEFAULT_FOLDER + "“ kann nicht umbenannt oder gelöscht werden.");
                return true;
            }
            String old = folder;
            if (item.getItemId() == 1) {
                askName("Ordner umbenennen", old, name -> runJob("Benenne um",
                        () -> tresor().renameFolder(old, name), renamed -> {
                            setStatus("✔ Umbenannt in „" + renamed + "“.");
                            loadFolders(renamed);
                        }));
            } else {
                confirm("Ordner löschen?", "Den Ordner „" + old + "“ mit allen Links, Notizen und Dateien löschen?",
                        "Löschen", () -> runJob("Lösche Ordner", () -> {
                            tresor().deleteFolder(old);
                            return true;
                        }, ok -> {
                            setStatus("✔ Ordner „" + old + "“ gelöscht.");
                            loadFolders(Tresor.DEFAULT_FOLDER);
                        }));
            }
            return true;
        });
        m.show();
    }

    // ================================================================= Links
    static final Pattern URL_IN_TEXT = Pattern.compile("(https?://\\S+|www\\.\\S+)");

    void pasteLink() {
        ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        ClipData clip = cm.getPrimaryClip();
        if (clip == null || clip.getItemCount() == 0) {
            setStatus("Zwischenablage ist leer.");
            return;
        }
        CharSequence text = clip.getItemAt(0).coerceToText(this);
        fillLink(text == null ? "" : text.toString(), null);
    }

    /** Text (z. B. aus „Teilen“) -> URL und ggf. Titel ins Link-Formular. */
    void fillLink(String text, String subject) {
        Matcher m = URL_IN_TEXT.matcher(text);
        String url = m.find() ? m.group(1) : text.trim();
        linkUrl.setText(url);
        String rest = text.replace(url, "").trim();
        if (subject != null && !subject.trim().isEmpty()) linkTitle.setText(subject.trim());
        else if (!rest.isEmpty() && rest.length() < 120 && linkTitle.getText().length() == 0) linkTitle.setText(rest);
    }

    void saveLink() {
        if (needToken()) return;
        String url = linkUrl.getText().toString(), title = linkTitle.getText().toString(),
                note = linkNote.getText().toString();
        if (url.trim().isEmpty()) {
            linkUrl.setError("Bitte einen Link eingeben.");
            return;
        }
        hideKeyboard();
        String f = folder;
        runJob("Speichere Link", () -> tresor().addLink(url, title, note), saved -> {
            linkUrl.setText("");
            linkTitle.setText("");
            linkNote.setText("");
            setStatus("✔ Link gespeichert in „" + f + "“.");
        });
    }

    // ================================================================ Notizen
    void saveNote() {
        if (needToken()) return;
        String title = noteTitle.getText().toString(), text = noteText.getText().toString();
        if (title.trim().isEmpty() && text.trim().isEmpty()) {
            noteText.setError("Die Notiz ist leer.");
            return;
        }
        hideKeyboard();
        String f = folder;
        runJob("Speichere Notiz", () -> tresor().addNote(title, text), path -> {
            noteTitle.setText("");
            noteText.setText("");
            setStatus("✔ Notiz gespeichert in „" + f + "“.");
        });
    }

    // ================================================================ Dateien
    void pickFiles() {
        if (needToken()) return;
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        startActivityForResult(i, PICK_FILES);
    }

    @Override
    protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != PICK_FILES || result != RESULT_OK || data == null) return;
        List<Uri> uris = new ArrayList<>();
        if (data.getClipData() != null) {
            for (int i = 0; i < data.getClipData().getItemCount(); i++) uris.add(data.getClipData().getItemAt(i).getUri());
        } else if (data.getData() != null) {
            uris.add(data.getData());
        }
        uploadFiles(uris);
    }

    String displayName(Uri uri) {
        try (Cursor c = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (c != null && c.moveToFirst() && !c.isNull(0)) return c.getString(0);
        } catch (Exception ignored) {
        }
        String last = uri.getLastPathSegment();
        return last == null ? "datei" : last;
    }

    long size(Uri uri) {
        try (Cursor c = getContentResolver().query(uri, new String[]{OpenableColumns.SIZE}, null, null, null)) {
            if (c != null && c.moveToFirst() && !c.isNull(0)) return c.getLong(0);
        } catch (Exception ignored) {
        }
        return -1;
    }

    void uploadFiles(List<Uri> uris) {
        if (uris.isEmpty() || needToken()) return;
        selectTab(2);
        String f = folder;
        Tresor t = tresor();
        fileInfo.setText("");
        StringBuilder log = new StringBuilder();
        runJob("Lade " + uris.size() + (uris.size() == 1 ? " Datei" : " Dateien") + " hoch", () -> {
            int ok = 0;
            for (Uri u : uris) {
                String name = displayName(u);
                ui.post(() -> setStatus("Lade hoch: " + name + " …"));
                try {
                    if (size(u) > Tresor.MAX_FILE_BYTES)
                        throw new IllegalArgumentException("zu groß (max. 70 MB)");
                    byte[] data;
                    try (InputStream in = getContentResolver().openInputStream(u)) {
                        data = GitHub.readBytes(in);
                    }
                    String path = t.addFile(name, data);
                    log.append("✔ ").append(path.substring(path.lastIndexOf('/') + 1)).append('\n');
                    ok++;
                } catch (Exception e) {
                    log.append("✖ ").append(name).append(": ").append(e.getMessage()).append('\n');
                }
                ui.post(() -> fileInfo.setText(log.toString()));
            }
            return ok;
        }, ok -> {
            fileInfo.setText(log.toString());
            setStatus("✔ " + ok + " von " + uris.size() + " hochgeladen in „" + f + "“.");
        });
    }

    // ================================================================ Teilen
    void handleShare(Intent intent) {
        if (intent == null) return;
        String action = intent.getAction();
        if (Intent.ACTION_SEND.equals(action)) {
            Uri stream = intent.getParcelableExtra(Intent.EXTRA_STREAM);
            String text = intent.getStringExtra(Intent.EXTRA_TEXT);
            if (stream != null) {
                List<Uri> l = new ArrayList<>();
                l.add(stream);
                confirmUpload(l);
            } else if (text != null && !TikTok.findLinks(text).isEmpty() && TikTok.LINK_RE.matcher(text).find()) {
                selectTab(TAB_TIKTOK);
                addTikTokLinks(text);
                setStatus("TikTok-Link übernommen – „⬇ Herunterladen“ tippen.");
            } else if (text != null) {
                selectTab(0);
                fillLink(text, intent.getStringExtra(Intent.EXTRA_SUBJECT));
                chooseFolder("Link speichern in …", f -> {
                    setStatus("Link übernommen – „Im Tresor speichern“ tippen (Ordner „" + f + "“).");
                    linkTitle.requestFocus();
                });
            }
        } else if (Intent.ACTION_SEND_MULTIPLE.equals(action)) {
            ArrayList<Uri> l = intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
            if (l != null) confirmUpload(l);
        }
        intent.setAction(null); // nicht nochmal verarbeiten (z. B. nach Drehen)
    }

    void confirmUpload(List<Uri> uris) {
        selectTab(2);
        if (!hasToken()) return;
        String what = uris.size() == 1 ? "„" + displayName(uris.get(0)) + "“" : uris.size() + " Dateien";
        chooseFolder(what + " hochladen in …", f -> uploadFiles(uris));
    }

    /** Ordner auswählen lassen (aktueller ist vorausgewählt), dann umschalten und done aufrufen. */
    void chooseFolder(String title, Done<String> done) {
        if (!hasToken()) return;
        Tresor t = tresor();
        runJob("Lade Ordner", t::listFolders, list -> {
            folders.clear();
            folders.addAll(list);
            folderAdapter.notifyDataSetChanged();
            String[] names = list.toArray(new String[0]);
            int[] pick = {Math.max(list.indexOf(folder), 0)};
            new AlertDialog.Builder(this).setTitle(title)
                    .setSingleChoiceItems(names, pick[0], (d, which) -> pick[0] = which)
                    .setPositiveButton("OK", (d, w) -> {
                        String f = names[pick[0]];
                        folderBoxUpdating = true;
                        folderBox.setSelection(pick[0]);
                        folderBox.post(() -> folderBoxUpdating = false);
                        if (!f.equals(folder)) switchFolder(f);
                        done.done(f);
                    })
                    .setNegativeButton("Abbrechen", null).show();
        });
    }

    // ================================================================ TikTok
    void addTikTokLinks(String text) {
        StringBuilder b = new StringBuilder(ttLinks.getText().toString().trim());
        for (String link : TikTok.findLinks(text)) {
            if (b.indexOf(link) >= 0) continue;
            if (b.length() > 0) b.append('\n');
            b.append(link);
        }
        ttLinks.setText(b.toString());
    }

    void pasteTikTok() {
        ClipData clip = ((ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE)).getPrimaryClip();
        CharSequence text = clip == null || clip.getItemCount() == 0 ? null : clip.getItemAt(0).coerceToText(this);
        if (text == null || TikTok.findLinks(text.toString()).isEmpty()) {
            setStatus("Kein TikTok-Link in der Zwischenablage.");
            return;
        }
        addTikTokLinks(text.toString());
    }

    void ttLog(String line) {
        ttLog.append(line + "\n");
    }

    /** Speichert eine Datei in Download/TikTok/<user> (öffentlicher Download-Ordner). */
    String saveToDownloads(String user, String name, String mime, TikTok.Info info, String url, TikTok.Progress pr)
            throws Exception {
        String sub = "TikTok/" + TikTok.safeName(user);
        if (Build.VERSION.SDK_INT >= 29) {
            android.content.ContentValues v = new android.content.ContentValues();
            v.put(android.provider.MediaStore.MediaColumns.DISPLAY_NAME, name);
            v.put(android.provider.MediaStore.MediaColumns.MIME_TYPE, mime);
            v.put(android.provider.MediaStore.MediaColumns.RELATIVE_PATH,
                    android.os.Environment.DIRECTORY_DOWNLOADS + "/" + sub);
            v.put(android.provider.MediaStore.MediaColumns.IS_PENDING, 1);
            android.content.ContentResolver cr = getContentResolver();
            Uri uri = cr.insert(android.provider.MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
            if (uri == null) throw new Exception("Download-Ordner nicht beschreibbar.");
            try (java.io.OutputStream out = cr.openOutputStream(uri)) {
                TikTok.download(url, out, pr);
            } catch (Exception e) {
                cr.delete(uri, null, null);
                throw e;
            }
            v.clear();
            v.put(android.provider.MediaStore.MediaColumns.IS_PENDING, 0);
            cr.update(uri, v, null, null);
            return "Download/" + sub + "/" + name;
        }
        File dir = new File(android.os.Environment.getExternalStoragePublicDirectory(
                android.os.Environment.DIRECTORY_DOWNLOADS), sub);
        if (!dir.isDirectory() && !dir.mkdirs()) throw new Exception("Download-Ordner nicht beschreibbar.");
        File f = new File(dir, name);
        for (int n = 2; f.exists(); n++) {
            int dot = name.lastIndexOf('.');
            f = new File(dir, name.substring(0, dot) + " (" + n + ")" + name.substring(dot));
        }
        try (FileOutputStream out = new FileOutputStream(f)) {
            TikTok.download(url, out, pr);
        } catch (Exception e) {
            f.delete();
            throw e;
        }
        android.media.MediaScannerConnection.scanFile(this, new String[]{f.getPath()}, null, null);
        return "Download/" + sub + "/" + f.getName();
    }

    void downloadTikTok() {
        List<String> links = TikTok.findLinks(ttLinks.getText().toString());
        if (links.isEmpty()) {
            ttLinks.setError("Bitte mindestens einen TikTok-Link einfügen.");
            return;
        }
        boolean toTresor = ttToTresor.isChecked(), keepLink = ttKeepLink.isChecked(), asMp3 = ttAsMp3.isChecked();
        if ((toTresor || keepLink) && needToken()) return;
        if (!toTresor && Build.VERSION.SDK_INT < 29
                && checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{android.Manifest.permission.WRITE_EXTERNAL_STORAGE}, ASK_STORAGE);
            return;
        }
        hideKeyboard();
        Tresor t = tresor();
        String f = folder;
        ttButton.setEnabled(false);
        ttLog("— " + links.size() + " Link(s) – Ziel: " + (toTresor ? "Tresor „" + f + "“" : "Download/TikTok"));
        runJob("TikTok", () -> {
            int ok = 0;
            java.util.Set<String> seen = new java.util.HashSet<>();
            for (int i = 0; i < links.size(); i++) {
                String prefix = "[" + (i + 1) + "/" + links.size() + "]", link = links.get(i);
                try {
                    ui.post(() -> setStatus("TikTok " + prefix + ": hole Infos …"));
                    TikTok.Info info = TikTok.fetchInfo(link);
                    if (!seen.add(info.id)) {
                        ui.post(() -> ttLog(prefix + " ↷ doppelt, übersprungen"));
                        continue;
                    }
                    if (toTresor && !asMp3 && info.size > Tresor.MAX_FILE_BYTES)
                        throw new Exception("zu groß für den Tresor (max. 70 MB) – bitte „Aufs Handy“ wählen");
                    List<String> urls = info.urls(), names = info.fileNames();
                    if (asMp3) {
                        // Am Handy gibt es kein FFmpeg – TikTok liefert den Ton des Beitrags selbst als MP3
                        if (info.music == null) throw new Exception("zu diesem Beitrag gibt es keinen Ton");
                        urls = java.util.Collections.singletonList(info.music);
                        names = java.util.Collections.singletonList(info.mp3Name());
                    }
                    for (int n = 0; n < urls.size(); n++) {
                        String part = urls.size() > 1 ? " Bild " + (n + 1) + "/" + urls.size() : "";
                        TikTok.Progress pr = (done, total) -> {
                            if (total > 0) ui.post(() -> setStatus("TikTok " + prefix + part + ": " + (done * 100 / total) + " % …"));
                        };
                        String mime = asMp3 ? "audio/mpeg" : info.video != null ? "video/mp4" : "image/jpeg";
                        if (toTresor) {
                            java.io.ByteArrayOutputStream buf = new java.io.ByteArrayOutputStream();
                            TikTok.download(urls.get(n), buf, pr);
                            ui.post(() -> setStatus("TikTok " + prefix + part + ": lade in den Tresor …"));
                            t.addFile(names.get(n), buf.toByteArray());
                        } else {
                            saveToDownloads(info.user, names.get(n), mime, info, urls.get(n), pr);
                        }
                    }
                    String kind = asMp3 ? "MP3" : info.video != null ? "Video" : urls.size() + " Bilder";
                    String title = info.title.length() > 60 ? info.title.substring(0, 60) : info.title;
                    ui.post(() -> ttLog(prefix + " ✔ @" + info.user + ": " + (title.isEmpty() ? info.id : title) + " (" + kind + ")"));
                    if (keepLink) {
                        String lt = ("TikTok @" + info.user + ": " + (info.title.length() > 80 ? info.title.substring(0, 80) : info.title))
                                .replaceAll("[: ]+$", "");
                        t.addLink(info.link(), lt, "");
                    }
                    ok++;
                } catch (Exception e) {
                    String shortLink = link.length() > 60 ? link.substring(0, 60) : link;
                    ui.post(() -> ttLog(prefix + " ✖ " + shortLink + ": " + e.getMessage()));
                }
            }
            return ok;
        }, ok -> {
            ttButton.setEnabled(true);
            String where = toTresor ? "im Tresor-Ordner „" + f + "“" : "in Download/TikTok";
            setStatus(ok > 0 ? "✔ TikTok: " + ok + " von " + links.size() + " gespeichert " + where + "."
                    : "✖ TikTok: nichts gespeichert.");
            if (ok > 0) ttLinks.setText("");
        }, err -> {
            ttButton.setEnabled(true);
            ttLog("✖ " + err.getMessage());
        });
    }

    @Override
    public void onRequestPermissionsResult(int request, String[] perms, int[] results) {
        super.onRequestPermissionsResult(request, perms, results);
        if (request != ASK_STORAGE) return;
        if (results.length > 0 && results[0] == android.content.pm.PackageManager.PERMISSION_GRANTED) downloadTikTok();
        else alert("TikTok", "Ohne Speicher-Erlaubnis kann das Video nicht aufs Handy. Alternativ „In den Tresor“ wählen.");
    }

    // ============================================================= Übersicht
    void loadOverview() {
        if (!hasToken()) return;
        Tresor t = tresor();
        runJob("Lade Übersicht", () -> {
            List<Object> items = new ArrayList<>();
            List<Tresor.Link> links = t.recentLinks();
            List<Tresor.Entry> notes = t.listNotes(), files = t.listFiles();
            items.add("LINKS (" + links.size() + ")");
            items.addAll(links);
            items.add("NOTIZEN (" + notes.size() + ")");
            items.addAll(notes);
            items.add("DATEIEN (" + files.size() + ")");
            items.addAll(files);
            return items;
        }, items -> {
            if (!t.folder.equals(folder)) return; // inzwischen anderer Ordner
            overviewAll.clear();
            overviewAll.addAll(items);
            applyFilter();
            if (searchBox.getText().toString().trim().isEmpty()) setStatus("Ordner „" + folder + "“");
        });
    }

    /** Übersicht nach Suchwörtern filtern (Titel, Adresse, Notiz bzw. Name). */
    void applyFilter() {
        String[] words = searchBox.getText().toString().toLowerCase(Locale.ROOT).trim().split("\\s+");
        boolean all = words.length == 1 && words[0].isEmpty();
        overviewItems.clear();
        String header = null;
        List<Object> group = new ArrayList<>();
        int found = 0;
        for (Object o : overviewAll) {
            if (o instanceof String) {
                if (header != null) found += addGroup(header, group);
                header = (String) o;
                group.clear();
                continue;
            }
            String hay = o instanceof Tresor.Link
                    ? ((Tresor.Link) o).title + " " + ((Tresor.Link) o).line
                    : ((Tresor.Entry) o).label + " " + ((Tresor.Entry) o).path;
            hay = hay.toLowerCase(Locale.ROOT);
            boolean ok = true;
            for (String w : words) if (!all && !hay.contains(w)) ok = false;
            if (ok) group.add(o);
        }
        if (header != null) found += addGroup(header, group);
        overviewAdapter.notifyDataSetChanged();
        if (!all) setStatus("🔍 " + found + " Treffer in „" + folder + "“");
    }

    int addGroup(String header, List<Object> group) {
        overviewItems.add(header.replaceAll("\\(\\d+\\)", "(" + group.size() + ")"));
        overviewItems.addAll(group);
        return group.size();
    }

    void openEntry(Object o) {
        if (o instanceof Tresor.Link) {
            openUrl(((Tresor.Link) o).url);
        } else if (o instanceof Tresor.Entry) {
            Tresor.Entry e = (Tresor.Entry) o;
            Tresor t = tresor();
            if (t.isNote(e.path)) {
                runJob("Lade Notiz", () -> t.readNote(e.path), text -> showNote(e, text));
            } else {
                openFile(e);
            }
        }
    }

    void showNote(Tresor.Entry e, String text) {
        TextView t = new TextView(this);
        t.setText(text);
        t.setTextIsSelectable(true);
        t.setTextColor(TEXT);
        t.setTextSize(15);
        t.setPadding(dp(20), dp(12), dp(20), dp(12));
        t.setMovementMethod(LinkMovementMethod.getInstance());
        android.text.util.Linkify.addLinks(t, android.text.util.Linkify.WEB_URLS);
        ScrollView s = new ScrollView(this);
        s.addView(t);
        new AlertDialog.Builder(this).setTitle(e.label).setView(s)
                .setPositiveButton("Schließen", null)
                .setNegativeButton("✎ Bearbeiten", (d, w) -> editEntry(e))
                .setNeutralButton("Kopieren", (d, w) -> {
                    ((ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE))
                            .setPrimaryClip(ClipData.newPlainText("Notiz", text));
                    setStatus("✔ Notiz kopiert.");
                }).show();
    }

    // ============================================================ Bearbeiten
    void entryMenu(Object o) {
        if (o instanceof String) return;
        String name = o instanceof Tresor.Link ? ((Tresor.Link) o).title : ((Tresor.Entry) o).label;
        new AlertDialog.Builder(this).setTitle(name)
                .setItems(new String[]{"✎ Bearbeiten", "🗑 Löschen"}, (d, which) -> {
                    if (which == 0) editEntry(o);
                    else askDelete(o);
                }).show();
    }

    /** Eintrag in der Übersicht sofort durch den geänderten ersetzen. */
    void replaceInOverview(Object old, Object neu) {
        int i = overviewAll.indexOf(old);
        if (i >= 0) overviewAll.set(i, neu);
        applyFilter();
    }

    LinearLayout dialogColumn() {
        LinearLayout l = column();
        l.setPadding(dp(20), dp(4), dp(20), 0);
        return l;
    }

    void editEntry(Object o) {
        if (o instanceof String || needToken()) return;
        Tresor t = tresor();
        if (o instanceof Tresor.Link) {
            Tresor.Link link = (Tresor.Link) o;
            String[] p = Tresor.parseLinkLine(link.line);
            if (p == null) p = new String[]{link.title, link.url, "", ""};
            LinearLayout l = dialogColumn();
            l.addView(label("Link (URL):"));
            EditText url = field("https://…", false);
            url.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
            url.setText(p[1]);
            l.addView(url);
            l.addView(label("Titel (optional):"));
            EditText title = field("", false);
            title.setText(p[0]);
            l.addView(title);
            l.addView(label("Notiz (optional):"));
            EditText note = field("", false);
            note.setText(p[2]);
            l.addView(note);
            ScrollView s = new ScrollView(this);
            s.addView(l);
            AlertDialog d = new AlertDialog.Builder(this).setTitle("Link bearbeiten").setView(s)
                    .setPositiveButton("Speichern", null).setNegativeButton("Abbrechen", null).create();
            d.setOnShowListener(x -> d.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                String u = url.getText().toString(), ti = title.getText().toString(), no = note.getText().toString();
                if (u.trim().isEmpty()) {
                    url.setError("Bitte einen Link eingeben.");
                    return;
                }
                d.dismiss();
                runJob("Speichere Link", () -> t.editLink(link, u, ti, no), newLine -> {
                    String[] np = Tresor.parseLinkLine(newLine);
                    String shown = ti.trim().isEmpty() ? np[1] : ti.trim();
                    replaceInOverview(link, new Tresor.Link(shown, np[1], newLine));
                    setStatus("✔ Link geändert: " + shown);
                });
            }));
            d.show();
        } else {
            Tresor.Entry e = (Tresor.Entry) o;
            if (t.isNote(e.path)) {
                runJob("Lade Notiz", () -> t.readNoteParts(e.path), parts -> editNoteDialog(t, e, parts));
            } else {
                String name = e.label;
                askName("Datei umbenennen", name, newName -> {
                    if (newName.trim().isEmpty() || newName.trim().equals(name)) return;
                    runJob("Benenne Datei um", () -> t.renameFile(e.path, newName), newPath -> {
                        String n = newPath.substring(newPath.lastIndexOf('/') + 1);
                        replaceInOverview(e, new Tresor.Entry(n, newPath));
                        setStatus("✔ Umbenannt in „" + n + "“");
                    });
                });
            }
        }
    }

    void editNoteDialog(Tresor t, Tresor.Entry e, String[] parts) {
        LinearLayout l = dialogColumn();
        l.addView(label("Titel:"));
        EditText title = field("", false);
        title.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        title.setText(parts[0]);
        l.addView(title);
        l.addView(label("Text:"));
        EditText text = field("", true);
        text.setMinLines(8);
        text.setText(parts[1]);
        l.addView(text);
        ScrollView s = new ScrollView(this);
        s.addView(l);
        AlertDialog d = new AlertDialog.Builder(this).setTitle("Notiz bearbeiten").setView(s)
                .setPositiveButton("Speichern", null).setNegativeButton("Abbrechen", null).create();
        d.setOnShowListener(x -> d.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String ti = title.getText().toString(), tx = text.getText().toString();
            if (ti.trim().isEmpty() && tx.trim().isEmpty()) {
                text.setError("Die Notiz ist leer.");
                return;
            }
            d.dismiss();
            runJob("Speichere Notiz", () -> t.editNote(e.path, ti, tx), newPath -> {
                replaceInOverview(e, new Tresor.Entry(Tresor.noteLabel(newPath.substring(newPath.lastIndexOf('/') + 1)), newPath));
                setStatus("✔ Notiz geändert: " + (ti.trim().isEmpty() ? "Notiz" : ti.trim()));
            });
        }));
        d.show();
    }

    File openDir() {
        File d = new File(getCacheDir(), "open");
        d.mkdirs();
        return d;
    }

    void cleanupOldDownloads() {
        File[] old = openDir().listFiles();
        if (old != null) for (File f : old) f.delete();
    }

    /** Datei herunterladen und mit passender App öffnen. */
    void openFile(Tresor.Entry e) {
        GitHub gh = client();
        runJob("Lade " + e.label, () -> {
            GitHub.FileData f = gh.getFile(e.path);
            if (f == null) throw new Exception("Die Datei gibt es nicht mehr.");
            File out = new File(openDir(), Tresor.safeFilename(e.label));
            try (FileOutputStream o = new FileOutputStream(out)) {
                o.write(f.data);
            }
            return out;
        }, file -> {
            String ext = MimeTypeMap.getFileExtensionFromUrl(Uri.encode(file.getName())).toLowerCase(Locale.ROOT);
            String type = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);
            Intent i = new Intent(Intent.ACTION_VIEW);
            i.setDataAndType(FilesProvider.uriFor(this, file), type != null ? type : "*/*");
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            try {
                startActivity(Intent.createChooser(i, "Öffnen mit"));
            } catch (Exception ex) {
                openUrl(gh.fileUrl(e.path));
            }
        });
    }

    void askDelete(Object o) {
        if (o instanceof String || needToken()) return;
        Tresor t = tresor();
        String name, what;
        Job<Boolean> job;
        if (o instanceof Tresor.Link) {
            Tresor.Link l = (Tresor.Link) o;
            name = l.title;
            what = "Link";
            job = () -> {
                t.deleteLink(l);
                return true;
            };
        } else {
            Tresor.Entry e = (Tresor.Entry) o;
            name = e.label;
            what = t.isNote(e.path) ? "Notiz" : "Datei";
            job = () -> {
                t.deleteEntry(e.path);
                return true;
            };
        }
        confirm(what + " löschen?", "„" + name + "“ wirklich löschen?", "Löschen", () ->
                runJob("Lösche " + what, job, ok -> {
                    overviewAll.remove(o);
                    applyFilter();
                    setStatus("✔ " + what + " gelöscht.");
                }));
    }

    // ============================================================ Einstellungen
    void openSettings() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setPadding(dp(20), dp(4), dp(20), 0);
        l.addView(label("GitHub-Repository (besitzer/name):"));
        EditText repo = field("", false);
        repo.setText(prefs.getString("repo", DEFAULT_REPO));
        l.addView(repo);
        l.addView(label("Branch (leer = main):"));
        EditText branch = field("main", false);
        branch.setText(prefs.getString("branch", DEFAULT_BRANCH).equals(DEFAULT_BRANCH) ? "" : prefs.getString("branch", ""));
        l.addView(branch);
        l.addView(label("GitHub-Token:"));
        EditText token = field("ghp_…", false);
        token.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        token.setText(prefs.getString("token", ""));
        l.addView(token);
        TextView link = new TextView(this);
        link.setText("Token erstellen (Haken bei „repo“) ↗");
        link.setTextColor(ACCENT);
        link.setPadding(0, dp(10), 0, dp(4));
        link.setOnClickListener(v -> openUrl(TOKEN_URL));
        l.addView(link);
        ScrollView s = new ScrollView(this);
        s.addView(l);

        AlertDialog d = new AlertDialog.Builder(this).setTitle("⚙ Einstellungen").setView(s)
                .setPositiveButton("Prüfen & speichern", null).setNegativeButton("Abbrechen", null).create();
        d.setOnShowListener(x -> d.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String r = repo.getText().toString().trim(), b = branch.getText().toString().trim(),
                    tk = token.getText().toString().trim();
            if (r.isEmpty() || !r.contains("/") || tk.isEmpty()) {
                token.setError("Bitte Repo (besitzer/name) und Token eintragen.");
                return;
            }
            String br = b.isEmpty() ? DEFAULT_BRANCH : b;
            d.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(false);
            runJob("Prüfe Zugang", () -> new GitHub(tk, r, br).check(), def -> {
                prefs.edit().putString("repo", r).putString("branch", br).putString("token", tk).apply();
                d.dismiss();
                setStatus("✔ Verbunden mit " + r);
                loadFolders(null);
                refreshBell();
            }, err -> {
                d.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(true);
                token.setError(err.getMessage());
            });
        }));
        d.show();
    }

    // ============================================================== Feedback
    void openFeedbackDialog() {
        if (needToken()) return;
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setPadding(dp(20), dp(4), dp(20), 0);
        TextView info = label("Wird als Issue gespeichert. Wenn du fertig bist: „🔔 Claude rufen“ tippen.");
        info.setTextColor(MUTED);
        l.addView(info);
        RadioGroup kinds = new RadioGroup(this);
        kinds.setOrientation(RadioGroup.HORIZONTAL);
        RadioButton vor = new RadioButton(this), feh = new RadioButton(this);
        vor.setText("💡 Vorschlag");
        feh.setText("🐞 Fehler");
        vor.setTextColor(TEXT);
        feh.setTextColor(TEXT);
        vor.setId(View.generateViewId());
        feh.setId(View.generateViewId());
        kinds.addView(vor);
        kinds.addView(feh);
        vor.setChecked(true);
        l.addView(kinds);
        l.addView(label("Titel:"));
        EditText title = field("", false);
        title.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        l.addView(title);
        l.addView(label("Beschreibung:"));
        EditText desc = field("", true);
        l.addView(desc);
        ScrollView s = new ScrollView(this);
        s.addView(l);

        AlertDialog d = new AlertDialog.Builder(this).setTitle("💡 Feedback").setView(s)
                .setPositiveButton("Senden", null).setNegativeButton("Abbrechen", null).create();
        d.setOnShowListener(x -> d.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String t = title.getText().toString().trim();
            if (t.isEmpty()) {
                title.setError("Bitte einen Titel eingeben.");
                return;
            }
            boolean bug = feh.isChecked();
            String text = desc.getText().toString().trim();
            String body = (text.isEmpty() ? "_Keine Beschreibung._" : text)
                    + "\n\n---\n_Gesendet aus Link-Tresor " + version() + " · Android " + Build.VERSION.RELEASE
                    + " (" + Build.MANUFACTURER + " " + Build.MODEL + ")_";
            GitHub gh = client();
            d.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(false);
            runJob("Speichere Feedback", () -> gh.createIssue((bug ? "🐞 " : "💡 ") + t, body,
                    "feedback", bug ? "fehler" : "vorschlag"), url -> {
                d.dismiss();
                String nr = url.isEmpty() ? "" : url.substring(url.lastIndexOf('/') + 1);
                setStatus("✔ Feedback #" + nr + " gespeichert. Noch mehr? Sonst „🔔 Claude rufen“.");
                if (nr.matches("\\d+")) feedbackCreated(nr, (bug ? "🐞 " : "💡 ") + t);
                else refreshBell();
            }, err -> {
                d.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(true);
                title.setError(err.getMessage());
            });
        }));
        d.show();
    }

    /** GitHub-Liste um lokal Bekanntes ergänzen (neue Issues/Kommentare erscheinen dort manchmal verzögert). */
    List<String[]> mergeFresh(List<String[]> items) {
        long now = System.currentTimeMillis();
        freshRung.values().removeIf(t -> t < now);
        freshFeedback.values().removeIf(v -> Long.parseLong(v[2]) < now);
        List<String[]> out = new ArrayList<>();
        java.util.Set<String> known = new java.util.HashSet<>();
        for (String[] it : items) {
            known.add(it[0]);
            out.add(new String[]{it[0], it[1], "1".equals(it[2]) || freshRung.containsKey(it[0]) ? "1" : "0"});
        }
        for (java.util.Map.Entry<String, String[]> e : freshFeedback.entrySet())
            if (!known.contains(e.getKey()))
                out.add(new String[]{e.getKey(), e.getValue()[0], freshRung.containsKey(e.getKey()) ? "1" : "0"});
        out.sort((x, y) -> Integer.parseInt(y[0]) - Integer.parseInt(x[0]));
        return out;
    }

    void showBell(List<String[]> items) {
        feedbackItems = items;
        if (bellButton == null) return;
        bellButton.setText(bellText());
        boolean fresh = bellText().contains("(") && bellText().startsWith("🔔");
        bellButton.setBackground(box(fresh ? ACCENT : CARD, fresh ? 0 : LINE));
    }

    /** Obere Leiste: Name + Version links, „🔔 Claude rufen“ in der Mitte, Menü ⋮ rechts. */
    void setupActionBar() {
        android.app.ActionBar bar = getActionBar();
        if (bar == null) return;
        bar.setSubtitle(version());
        bellButton = button("", CARD, v -> ringClaude());
        bellButton.setTextSize(14);
        bellButton.setMinHeight(dp(40));
        bellButton.setMinimumHeight(dp(40));
        bellButton.setPadding(dp(12), 0, dp(12), 0);
        bar.setCustomView(bellButton, new android.app.ActionBar.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, dp(40), Gravity.CENTER));
        bar.setDisplayShowCustomEnabled(true);
        showBell(feedbackItems);
    }

    String bellText() {
        int fresh = 0;
        for (String[] it : feedbackItems) if (!"1".equals(it[2])) fresh++;
        if (fresh > 0) return "🔔 Claude rufen (" + fresh + ")";
        if (!feedbackItems.isEmpty()) return "⏳ Claude arbeitet (" + feedbackItems.size() + ")";
        return "🔔 Claude rufen";
    }

    void feedbackCreated(String nr, String title) {
        freshFeedback.put(nr, new String[]{title, String.valueOf(System.currentTimeMillis() + FRESH_MS)});
        showBell(mergeFresh(feedbackItems));
        refreshBell();
    }

    void refreshBell() {
        if (!hasToken()) return;
        GitHub gh = client();
        runJob(null, gh::openFeedback, items -> {
            checkFinished(items);
            showBell(mergeFresh(items));
        }, err -> {
        });
    }

    /** Gerufene Feedbacks, die nicht mehr offen sind, hat Claude erledigt -> Bescheid geben. */
    void checkFinished(List<String[]> items) {
        java.util.Set<String> openNow = new java.util.HashSet<>();
        java.util.Map<String, String> nowRung = new java.util.TreeMap<>();
        for (String[] it : items) {
            openNow.add(it[0]);
            if ("1".equals(it[2]) || freshRung.containsKey(it[0])) nowRung.put(it[0], it[1]);
        }
        java.util.Map<String, String> known = rungOpen;
        rungOpen = nowRung;
        if (known == null) return; // erster Abgleich nach dem Start
        StringBuilder done = new StringBuilder(), refs = new StringBuilder();
        for (java.util.Map.Entry<String, String> e : known.entrySet()) {
            if (openNow.contains(e.getKey())) continue;
            done.append("  #").append(e.getKey()).append("  ").append(e.getValue()).append('\n');
            refs.append(refs.length() > 0 ? ", #" : "#").append(e.getKey());
        }
        if (done.length() == 0) return;
        setStatus("✔ Claude hat erledigt: " + refs);
        checkUpdateQuietly();
        alert("✔ Claude ist fertig", done + "\nNeue Versionen holst du über ⋮ → „⬆ Update“ "
                + "(am PC über „⬆ Update“). Details stehen im jeweiligen Issue.");
    }

    void ringClaude() {
        if (needToken()) return;
        GitHub gh = client();
        runJob("Lade offenes Feedback", gh::openFeedback, loaded -> {
            List<String[]> items = mergeFresh(loaded);
            showBell(items);
            if (items.isEmpty()) {
                alert("Link-Tresor", "Es gibt gerade kein offenes Feedback.\n\nErst über „💡 Feedback“ etwas eintragen, dann rufen.");
                return;
            }
            List<String[]> todo = new ArrayList<>();
            for (String[] it : items) if (!"1".equals(it[2])) todo.add(it);
            boolean again = todo.isEmpty();
            if (again) todo.addAll(items);
            StringBuilder lines = new StringBuilder(), refs = new StringBuilder(), list = new StringBuilder();
            for (String[] it : todo) {
                lines.append("  #").append(it[0]).append("  ").append(it[1]).append('\n');
                if (refs.length() > 0) refs.append(", ");
                refs.append('#').append(it[0]);
                list.append("\n- #").append(it[0]).append(' ').append(it[1]);
            }
            String text = GitHub.BELL_PREFIX + " " + refs + "\n" + list;
            String question = again
                    ? "Claude wurde für diese Feedbacks schon gerufen und arbeitet daran:\n\n" + lines
                    + "\nFertige Änderungen kommen über „⬆ Update“. Trotzdem nochmal rufen?"
                    : "Claude rufen, um diese " + todo.size() + " Feedbacks umzusetzen?\n\n" + lines;
            confirm("Claude rufen?", question, "Rufen", () -> runJob("Rufe Claude", () -> gh.ringBell(text), ok -> {
                if (ok) {
                    long until = System.currentTimeMillis() + FRESH_MS;
                    for (String[] it : todo) freshRung.put(it[0], until);
                    showBell(mergeFresh(feedbackItems));
                    setStatus("🔔 Claude wurde gerufen (" + refs + "). Neue Version später über „⬆ Update“.");
                } else {
                    alert("Link-Tresor", "Kein Feedback-Kanal gefunden (Pull Request „feedback-kanal“ fehlt).");
                }
            }));
        });
    }

    // ================================================================ Update
    /** Beim Start leise prüfen; bei neuer Version Hinweis in Statuszeile + Menü. */
    /** Client für das öffentliche App-Repo (Releases/Updates). */
    GitHub appClient() {
        return new GitHub(prefs.getString("token", ""), APP_REPO, "");
    }

    void checkUpdateQuietly() {
        GitHub gh = appClient();
        runJob(null, () -> gh.release(RELEASE_TAG), release -> {
            String latest = release == null ? "" : release.optString("target_commitish", "");
            updateAvailable = !latest.isEmpty() && !latest.equals(BuildConfig.BUILD_SHA) && !"dev".equals(BuildConfig.BUILD_SHA);
            invalidateOptionsMenu();
            if (updateAvailable) {
                setStatus("⬆ Neue Version verfügbar – oben ⋮ → „Update verfügbar!“");
                android.widget.Toast.makeText(this, "⬆ Neue Link-Tresor-Version verfügbar", android.widget.Toast.LENGTH_LONG).show();
            }
        }, err -> {
        });
    }

    void checkUpdate() {
        if (needToken()) return;
        GitHub gh = appClient();
        runJob("Suche Update", () -> gh.release(RELEASE_TAG), release -> {
            JSONObject asset = null;
            if (release != null) {
                JSONArray assets = release.optJSONArray("assets");
                for (int i = 0; assets != null && i < assets.length(); i++)
                    if (APK_NAME.equals(assets.optJSONObject(i).optString("name"))) asset = assets.optJSONObject(i);
            }
            if (asset == null) {
                alert("Update", "Noch keine Handy-Version auf GitHub gefunden.");
                return;
            }
            String latest = release.optString("target_commitish", "");
            if (latest.equals(BuildConfig.BUILD_SHA)) {
                alert("Update", "Du hast schon die neueste Version (" + version() + ").");
                return;
            }
            String shortSha = latest.substring(0, Math.min(7, latest.length()));
            JSONObject a = asset;
            confirm("Update verfügbar", "Neue Version " + shortSha + " herunterladen und installieren?\n\n"
                    + "(Deine Einstellungen bleiben erhalten.)", "Installieren", () -> downloadUpdate(gh, a));
        });
    }

    void downloadUpdate(GitHub gh, JSONObject asset) {
        if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
            confirm("Erlaubnis nötig", "Damit sich die App selbst aktualisieren kann, bitte im nächsten Fenster "
                    + "„Aus dieser Quelle zulassen“ einschalten und dann nochmal „⬆ Update“ tippen.", "Weiter", () ->
                    startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                            Uri.parse("package:" + getPackageName()))));
            return;
        }
        File apk = new File(openDir(), APK_NAME);
        runJob("Lade Update herunter", () -> {
            gh.downloadAsset(asset.getLong("id"), apk, (done, total) -> {
                if (total > 0) ui.post(() -> setStatus("Lade Update herunter … " + (done * 100 / total) + " %"));
            });
            return apk;
        }, file -> {
            setStatus("Installiere Update …");
            Intent i = new Intent(Intent.ACTION_VIEW);
            i.setDataAndType(FilesProvider.uriFor(this, file), "application/vnd.android.package-archive");
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(i);
        });
    }
}
