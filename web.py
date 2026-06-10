"""
PES Lobby Web — Supabase PostgreSQL + Telegram webhook
"""
import os, uuid, asyncio, threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

load_dotenv()
app = Flask(__name__)

BOT_TOKEN   = os.getenv("BOT_TOKEN", "")
WEBHOOK_URL = "https://pes21t99.onrender.com/tg_webhook"
_DB_URL     = os.getenv("DATABASE_URL", "")

# ── Bot event loop ─────────────────────────────────────────────────────────────
_bot_loop = asyncio.new_event_loop()
_bot_app  = None

def _run_loop():
    asyncio.set_event_loop(_bot_loop)
    _bot_loop.run_forever()

threading.Thread(target=_run_loop, daemon=True).start()

def _async(coro):
    return asyncio.run_coroutine_threadsafe(coro, _bot_loop).result(timeout=30)

async def _init_bot():
    global _bot_app
    if not BOT_TOKEN:
        print("[BOT] No BOT_TOKEN, skipping", flush=True)
        return
    try:
        from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                                   ConversationHandler, MessageHandler, filters)
        from bot import (cmd_start, cmd_register, cmd_ready, cmd_cancel, cmd_profile,
                         cmd_lobby, cb_host_them, cb_host_me, cmd_help, cmd_setlink,
                         got_ingame, got_platform, got_tier, got_parsec,
                         cancel as conv_cancel,
                         ASK_INGAME, ASK_PLATFORM, ASK_TIER, ASK_PARSEC)

        application = Application.builder().token(BOT_TOKEN).build()

        conv = ConversationHandler(
            entry_points=[CommandHandler("register", cmd_register)],
            states={
                ASK_INGAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_ingame)],
                ASK_PLATFORM: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_platform)],
                ASK_TIER:     [MessageHandler(filters.TEXT & ~filters.COMMAND, got_tier)],
                ASK_PARSEC:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_parsec)],
            },
            fallbacks=[CommandHandler("cancel", conv_cancel)],
        )
        application.add_handler(conv)
        application.add_handler(CommandHandler("start",   cmd_start))
        application.add_handler(CommandHandler("help",    cmd_help))
        application.add_handler(CommandHandler("setlink", cmd_setlink))
        application.add_handler(CommandHandler("ready",   cmd_ready))
        application.add_handler(CommandHandler("cancel",  cmd_cancel))
        application.add_handler(CommandHandler("profile", cmd_profile))
        application.add_handler(CommandHandler("timdoi",  cmd_lobby))
        application.add_handler(CallbackQueryHandler(cb_host_them, pattern=r"^host_them:\d+$"))
        application.add_handler(CallbackQueryHandler(cb_host_me,   pattern=r"^host_me:\d+$"))

        await application.initialize()
        await application.start()
        await application.bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        _bot_app = application
        print(f"[BOT] Webhook ready: {WEBHOOK_URL}", flush=True)
    except Exception as e:
        import traceback
        print(f"[BOT ERROR] {e}", flush=True)
        traceback.print_exc()


@app.route("/tg_webhook", methods=["POST"])
def tg_webhook():
    if not _bot_app:
        return "not ready", 503
    try:
        from telegram import Update
        data   = request.get_json(force=True, silent=True) or {}
        update = Update.de_json(data, _bot_app.bot)
        _async(_bot_app.process_update(update))
    except Exception as e:
        print(f"[WEBHOOK ERR] {e}", flush=True)
    return "ok"


# ── DB helpers ─────────────────────────────────────────────────────────────────

def get_db():
    url = _DB_URL
    if url and "sslmode" not in url:
        url += "?sslmode=require"
    return psycopg2.connect(url)


def init_db():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    web_id       TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    ingame_name  TEXT DEFAULT '',
                    tier         TEXT DEFAULT 'Tier 3',
                    parsec_link  TEXT DEFAULT '',
                    is_ready     INTEGER DEFAULT 0,
                    matched_with TEXT,
                    match_link   TEXT,
                    updated_at   TEXT,
                    last_seen    TEXT
                )
            """)
        conn.commit()
        print("[DB] Supabase PostgreSQL ready", flush=True)
    finally:
        conn.close()


def get_player(wid):
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM players WHERE web_id=%s", (wid,))
            r = cur.fetchone()
            return dict(r) if r else None
    finally:
        conn.close()


def auth(req):
    wid = req.headers.get("X-Web-Id", "").strip()
    if not wid:
        return None, None
    return wid, get_player(wid)


# ── Routes ─────────────────────────────────────────────────────────────────────

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

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO players (web_id, display_name, ingame_name, tier, parsec_link, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT(web_id) DO UPDATE SET
                    display_name=EXCLUDED.display_name,
                    ingame_name=EXCLUDED.ingame_name,
                    tier=EXCLUDED.tier,
                    parsec_link=EXCLUDED.parsec_link,
                    updated_at=EXCLUDED.updated_at
            """, (wid, name, ingame,
                  d.get("tier", "Tier 3"),
                  d.get("parsec_link", ""),
                  datetime.now().isoformat()))
        conn.commit()
    finally:
        conn.close()

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

    now    = datetime.now().isoformat()
    cutoff = (datetime.now() - timedelta(seconds=35)).isoformat()

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE players SET last_seen=%s WHERE web_id=%s", (now, wid))
            cur.execute("SELECT COUNT(*) FROM players WHERE last_seen >= %s", (cutoff,))
            count = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return jsonify({"online": count})


@app.route("/api/lobby")
def lobby():
    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM players WHERE is_ready=1 ORDER BY updated_at DESC"
            )
            rows = cur.fetchall()
    finally:
        conn.close()
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

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE players
                SET is_ready=1, matched_with=NULL, match_link=NULL, updated_at=%s
                WHERE web_id=%s
            """, (datetime.now().isoformat(), wid))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/cancel", methods=["POST"])
def cancel():
    wid, _ = auth(request)
    if not wid:
        return jsonify({"error": "Chưa đăng ký"}), 401

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE players SET is_ready=0, matched_with=NULL, match_link=NULL WHERE web_id=%s",
                (wid,)
            )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/connect", methods=["POST"])
def connect():
    wid, me = auth(request)
    if not me:
        return jsonify({"error": "Chưa đăng ký"}), 401

    d          = request.json or {}
    target_wid = d.get("target_id", "")
    host       = d.get("host", "them")

    conn = get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM players WHERE web_id=%s AND is_ready=1 AND matched_with IS NULL",
                (target_wid,)
            )
            target = cur.fetchone()
            if not target:
                return jsonify({"error": "Slot đã bị khoá!"}), 409

            target = dict(target)
            link_for_me     = target["parsec_link"] if host == "them" else None
            link_for_target = me["parsec_link"]     if host == "me"   else None
            now = datetime.now().isoformat()

            cur.execute(
                "UPDATE players SET is_ready=0, matched_with=%s, match_link=%s, updated_at=%s WHERE web_id=%s",
                (wid, link_for_target, now, target_wid)
            )
            cur.execute(
                "UPDATE players SET is_ready=0, matched_with=%s, match_link=%s, updated_at=%s WHERE web_id=%s",
                (target_wid, link_for_me, now, wid)
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"ok": True, "link": link_for_me, "opponent": target["display_name"]})


if __name__ == "__main__":
    init_db()
    _async(_init_bot())
    port = int(os.environ.get("PORT", 5000))
    print(f"[WEB] Starting on port {port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
