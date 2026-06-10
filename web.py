"""
PES Lobby Web — UUID localStorage (no login required)
"""
import os, sqlite3, uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
WEB_DB = "pes_web.db"


def get_db():
    conn = sqlite3.connect(WEB_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                web_id       TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                ingame_name  TEXT NOT NULL,
                tier         TEXT NOT NULL DEFAULT 'Tier 3',
                parsec_link  TEXT DEFAULT '',
                is_ready     INTEGER DEFAULT 0,
                matched_with TEXT,
                match_link   TEXT,
                updated_at   TEXT
            )
        """)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(players)")}
        for col, defn in [("parsec_link","TEXT DEFAULT ''"),
                          ("matched_with","TEXT"), ("match_link","TEXT"),
                          ("last_seen","TEXT")]:
            if col not in cols:
                conn.execute(f"ALTER TABLE players ADD COLUMN {col} {defn}")


def get_player(wid):
    with get_db() as conn:
        r = conn.execute("SELECT * FROM players WHERE web_id=?", (wid,)).fetchone()
        return dict(r) if r else None


def auth(req):
    """Lấy web_id từ header, trả về (wid, player) hoặc (None, None)."""
    wid = req.headers.get("X-Web-Id", "").strip()
    if not wid:
        return None, None
    return wid, get_player(wid)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/register", methods=["POST"])
def register():
    d   = request.json or {}
    wid = d.get("web_id") or str(uuid.uuid4())

    name   = (d.get("display_name") or "").strip()
    ingame = (d.get("ingame_name")  or "").strip()
    if not name:
        return jsonify({"error": "Thiếu tên hiển thị"}), 400

    with get_db() as conn:
        conn.execute("""
            INSERT INTO players (web_id, display_name, ingame_name, tier, parsec_link, updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(web_id) DO UPDATE SET
                display_name=excluded.display_name,
                ingame_name=excluded.ingame_name,
                tier=excluded.tier,
                parsec_link=excluded.parsec_link,
                updated_at=excluded.updated_at
        """, (wid, name, ingame,
              d.get("tier","Tier 3"),
              d.get("parsec_link",""),
              datetime.now().isoformat()))

    return jsonify({"ok": True, "web_id": wid, "profile": get_player(wid)})


@app.route("/api/profile")
def profile():
    wid, player = auth(request)
    if not player:
        return jsonify({"error": "not found"}), 404
    return jsonify(player)


@app.route("/api/ping", methods=["POST"])
def ping():
    wid, player = auth(request)
    if not player:
        return jsonify({"error": "not found"}), 404
    now = datetime.now().isoformat()
    cutoff = (datetime.now() - timedelta(seconds=35)).isoformat()
    with get_db() as conn:
        conn.execute("UPDATE players SET last_seen=? WHERE web_id=?", (now, wid))
        count = conn.execute(
            "SELECT COUNT(*) FROM players WHERE last_seen >= ?", (cutoff,)
        ).fetchone()[0]
    return jsonify({"online": count})


@app.route("/api/lobby")
def lobby():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM players WHERE is_ready=1 ORDER BY updated_at DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/status")
def status():
    wid, player = auth(request)
    if not player:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "is_ready":     player["is_ready"],
        "matched_with": player["matched_with"],
        "match_link":   player["match_link"],
    })


@app.route("/api/ready", methods=["POST"])
def set_ready():
    wid, player = auth(request)
    if not player:
        return jsonify({"error": "Chưa đăng ký"}), 401
    with get_db() as conn:
        conn.execute("""
            UPDATE players
            SET is_ready=1, matched_with=NULL, match_link=NULL, updated_at=?
            WHERE web_id=?
        """, (datetime.now().isoformat(), wid))
    return jsonify({"ok": True})


@app.route("/api/cancel", methods=["POST"])
def cancel():
    wid, _ = auth(request)
    if not wid:
        return jsonify({"error": "Chưa đăng ký"}), 401
    with get_db() as conn:
        conn.execute(
            "UPDATE players SET is_ready=0, matched_with=NULL, match_link=NULL WHERE web_id=?",
            (wid,)
        )
    return jsonify({"ok": True})


@app.route("/api/connect", methods=["POST"])
def connect():
    wid, me = auth(request)
    if not me:
        return jsonify({"error": "Chưa đăng ký"}), 401

    d          = request.json or {}
    target_wid = d.get("target_id", "")
    host       = d.get("host", "them")

    with get_db() as conn:
        target = conn.execute(
            "SELECT * FROM players WHERE web_id=? AND is_ready=1 AND matched_with IS NULL",
            (target_wid,)
        ).fetchone()
        if not target:
            return jsonify({"error": "Slot đã bị khoá!"}), 409

        target = dict(target)
        link_for_me     = target["parsec_link"] if host == "them" else None
        link_for_target = me["parsec_link"]     if host == "me"   else None
        now = datetime.now().isoformat()

        conn.execute(
            "UPDATE players SET is_ready=0, matched_with=?, match_link=?, updated_at=? WHERE web_id=?",
            (wid, link_for_target, now, target_wid)
        )
        conn.execute(
            "UPDATE players SET is_ready=0, matched_with=?, match_link=?, updated_at=? WHERE web_id=?",
            (target_wid, link_for_me, now, wid)
        )

    return jsonify({"ok": True, "link": link_for_me, "opponent": target["display_name"]})


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    print(f"Web chay tai http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
