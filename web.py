"""
PES Lobby Web — Supabase PostgreSQL + Telegram webhook
V4: A1-A3, B1-B3, C1-C2, D1-D3
"""
import os, uuid, asyncio, threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

load_dotenv()
app = Flask(__name__)

BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
WEBHOOK_URL   = "https://pes21t99.onrender.com/tg_webhook"
_DB_URL       = os.getenv("DATABASE_URL", "")
GROUP_CHAT_ID  = os.getenv("GROUP_CHAT_ID", "")
GROUP_TOPIC_ID = os.getenv("GROUP_TOPIC_ID", "")

# ── Bot event loop ─────────────────────────────────────────────────────────────
_bot_loop = asyncio.new_event_loop()
_bot_app  = None

def _run_loop():
    asyncio.set_event_loop(_bot_loop)
    _bot_loop.run_forever()

threading.Thread(target=_run_loop, daemon=True).start()

def _async(coro):
    return asyncio.run_coroutine_threadsafe(coro, _bot_loop).result(timeout=30)

def _fire(coro):
    asyncio.run_coroutine_threadsafe(coro, _bot_loop)

async def _bot_send(chat_id, text, reply_markup=None):
    if _bot_app and chat_id:
        try:
            kwargs = dict(
                chat_id=chat_id, text=text,
                parse_mode="Markdown", disable_web_page_preview=True
            )
            if GROUP_TOPIC_ID:
                kwargs["message_thread_id"] = int(GROUP_TOPIC_ID)
            if reply_markup:
                kwargs["reply_markup"] = reply_markup
            await _bot_app.bot.send_message(**kwargs)
        except Exception as ex:
            print(f"[BOT SEND ERR] {ex}", flush=True)

async def _send_lobby_notify(name):
    if not _bot_app or not GROUP_CHAT_ID:
        return
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 Vào Lobby", url="https://t.me/pes21t99bot/lobby")
    ]])
    try:
        kwargs = dict(
            chat_id=GROUP_CHAT_ID,
            text=f"*{name}* đang tìm đối, ai vào không!",
            parse_mode="Markdown", disable_web_page_preview=True,
            reply_markup=kb
        )
        if GROUP_TOPIC_ID:
            kwargs["message_thread_id"] = int(GROUP_TOPIC_ID)
        msg = await _bot_app.bot.send_message(**kwargs)
        await asyncio.sleep(60)
        await _bot_app.bot.delete_message(chat_id=GROUP_CHAT_ID, message_id=msg.message_id)
    except Exception as ex:
        print(f"[BOT SEND ERR] {ex}", flush=True)

async def _notify_subscribers(entering_name, entering_wid):
    conn = get_db()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT web_id FROM players WHERE notify_me=1 AND web_id != %s",
                (entering_wid,)
            )
            subs = [r["web_id"] for r in cur.fetchall()]
    finally:
        conn.close()
    for wid in subs:
        if wid.startswith("tg_"):
            await _bot_send(wid[3:],
                f"🔔 *{entering_name}* vào lobby tìm đối!\n\nMở app để ghép trận ngay!")

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


# ── DB ─────────────────────────────────────────────────────────────────────────

def get_db():
    url = _DB_URL
    if url and "sslmode" not in url:
        url += "?sslmode=require"
    return psycopg.connect(url, prepare_threshold=None)


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
                    last_seen    TEXT,
                    notify_me    INTEGER DEFAULT 0,
                    thumbs_up    INTEGER DEFAULT 0,
                    thumbs_down  INTEGER DEFAULT 0,
                    status       TEXT DEFAULT 'idle'
                )
            """)
            for col, defn in [
                ("notify_me",   "INTEGER DEFAULT 0"),
                ("thumbs_up",   "INTEGER DEFAULT 0"),
                ("thumbs_down", "INTEGER DEFAULT 0"),
                ("status",      "TEXT DEFAULT 'idle'"),
            ]:
                cur.execute(f"ALTER TABLE players ADD COLUMN IF NOT EXISTS {col} {defn}")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    id         SERIAL PRIMARY KEY,
                    p1_web_id  TEXT NOT NULL,
                    p1_name    TEXT NOT NULL,
                    p2_web_id  TEXT NOT NULL,
                    p2_name    TEXT NOT NULL,
                    matched_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id             SERIAL PRIMARY KEY,
                    web_id         TEXT NOT NULL,
                    display_name   TEXT NOT NULL,
                    scheduled_time TEXT NOT NULL,
                    note           TEXT DEFAULT '',
                    created_at     TEXT NOT NULL
                )
            """)
        conn.commit()
        print("[DB] Supabase PostgreSQL ready", flush=True)
    finally:
        conn.close()


def get_player(wid):
    conn = get_db()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
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


def _record_match(cur, wid1, name1, wid2, name2):
    now = datetime.now().isoformat()
    cur.execute("""
        INSERT INTO matches (p1_web_id, p1_name, p2_web_id, p2_name, matched_at)
        VALUES (%s, %s, %s, %s, %s)
    """, (wid1, name1, wid2, name2, now))
    cur.execute(
        "UPDATE players SET status='busy' WHERE web_id=%s OR web_id=%s",
        (wid1, wid2)
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/register", methods=["POST"])
def register():
    d      = request.json or {}
    wid    = d.get("web_id") or str(uuid.uuid4())
    name   = (d.get("display_name") or "").strip()
    ingame = (d.get("ingame_name")  or "").strip()
    if not name:
        return jsonify({"error": "Thiếu tên hiển thị"}), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO players (web_id, display_name, ingame_name, tier, parsec_link,
                                     updated_at, status)
                VALUES (%s,%s,%s,%s,%s,%s,'idle')
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
    cutoff = (datetime.now() - timedelta(minutes=5)).isoformat()
    conn = get_db()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM players
                WHERE is_ready=1
                   OR (status='busy' AND last_seen >= %s)
                ORDER BY is_ready DESC, updated_at ASC
            """, (cutoff,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/status")
def status():
    wid, player = auth(request)
    if not player:
        return jsonify({"error": "not found"}), 404
    result = {
        "is_ready":     player["is_ready"],
        "matched_with": player["matched_with"],
        "match_link":   player["match_link"],
    }
    if player["matched_with"]:
        opp = get_player(player["matched_with"])
        if opp:
            result["opponent_name"] = opp["display_name"]
            result["opponent_id"]   = opp["web_id"]
    return jsonify(result)


@app.route("/api/setlink", methods=["POST"])
def setlink():
    wid, player = auth(request)
    if not player:
        return jsonify({"error": "Chưa đăng ký"}), 401
    link = (request.json or {}).get("parsec_link", "").strip()
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE players SET parsec_link=%s WHERE web_id=%s", (link, wid))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "parsec_link": link})


@app.route("/api/ready", methods=["POST"])
def set_ready():
    wid, me = auth(request)
    if not me:
        return jsonify({"error": "Chưa đăng ký"}), 401
    d    = request.json or {}
    auto = d.get("auto", False)
    conn = get_db()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            now = datetime.now().isoformat()
            cur.execute("""
                UPDATE players
                SET is_ready=1, matched_with=NULL, match_link=NULL,
                    status='waiting', updated_at=%s
                WHERE web_id=%s
            """, (now, wid))
            if auto:
                me_has_link = bool(me.get("parsec_link"))
                link_filter = "" if me_has_link else "AND (parsec_link IS NOT NULL AND parsec_link != '')"
                cur.execute(f"""
                    SELECT * FROM players
                    WHERE is_ready=1 AND web_id != %s AND matched_with IS NULL
                    {link_filter}
                    ORDER BY updated_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED
                """, (wid,))
                opp = cur.fetchone()
                if opp:
                    opp = dict(opp)
                    t   = datetime.now().isoformat()
                    if opp.get("parsec_link"):
                        link_for_me  = opp["parsec_link"]
                        link_for_opp = None
                    else:
                        link_for_me  = None
                        link_for_opp = me.get("parsec_link") or None
                    cur.execute(
                        "UPDATE players SET is_ready=0, matched_with=%s, match_link=%s, updated_at=%s WHERE web_id=%s",
                        (wid, link_for_opp, t, opp["web_id"])
                    )
                    cur.execute(
                        "UPDATE players SET is_ready=0, matched_with=%s, match_link=%s, updated_at=%s WHERE web_id=%s",
                        (opp["web_id"], link_for_me, t, wid)
                    )
                    _record_match(cur, wid, me["display_name"], opp["web_id"], opp["display_name"])
                    conn.commit()
                    return jsonify({
                        "ok": True, "matched": True,
                        "opponent": opp["display_name"],
                        "opponent_id": opp["web_id"],
                        "link": link_for_me,
                    })
        conn.commit()
    finally:
        conn.close()
    _fire(_send_lobby_notify(me["display_name"]))
    _fire(_notify_subscribers(me["display_name"], wid))
    return jsonify({"ok": True, "matched": False})


@app.route("/api/cancel", methods=["POST"])
def cancel():
    wid, _ = auth(request)
    if not wid:
        return jsonify({"error": "Chưa đăng ký"}), 401
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE players
                SET is_ready=0, matched_with=NULL, match_link=NULL, status='idle'
                WHERE web_id=%s
            """, (wid,))
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
        with conn.cursor(row_factory=dict_row) as cur:
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
            _record_match(cur, wid, me["display_name"], target_wid, target["display_name"])
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "link": link_for_me, "opponent": target["display_name"],
                    "opponent_id": target_wid})


# ── A2: Notify-me toggle ───────────────────────────────────────────────────────

@app.route("/api/notify-me", methods=["POST"])
def notify_me_toggle():
    wid, player = auth(request)
    if not player:
        return jsonify({"error": "Chưa đăng ký"}), 401
    val = 1 if (request.json or {}).get("enabled") else 0
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE players SET notify_me=%s WHERE web_id=%s", (val, wid))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "notify_me": val})


# ── A3: Schedules ─────────────────────────────────────────────────────────────

@app.route("/api/schedules")
def get_schedules():
    conn = get_db()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM schedules ORDER BY scheduled_time ASC")
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/schedules", methods=["POST"])
def add_schedule():
    wid, player = auth(request)
    if not player:
        return jsonify({"error": "Chưa đăng ký"}), 401
    d     = request.json or {}
    stime = (d.get("scheduled_time") or "").strip()
    note  = (d.get("note") or "").strip()[:100]
    if not stime:
        return jsonify({"error": "Thiếu thời gian"}), 400
    conn = get_db()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                INSERT INTO schedules (web_id, display_name, scheduled_time, note, created_at)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            """, (wid, player["display_name"], stime, note, datetime.now().isoformat()))
            new_id = cur.fetchone()["id"]
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True, "id": new_id})


@app.route("/api/schedules/<int:sid>", methods=["DELETE"])
def del_schedule(sid):
    wid, _ = auth(request)
    if not wid:
        return jsonify({"error": "Chưa đăng ký"}), 401
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM schedules WHERE id=%s AND web_id=%s", (sid, wid))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


# ── B1: Rematch ────────────────────────────────────────────────────────────────

@app.route("/api/rematch", methods=["POST"])
def rematch():
    wid, me = auth(request)
    if not me:
        return jsonify({"error": "Chưa đăng ký"}), 401
    opp_wid = (request.json or {}).get("opponent_id", "")
    if not opp_wid or not opp_wid.startswith("tg_"):
        return jsonify({"ok": False, "msg": "Chỉ gửi được cho người dùng Telegram"})
    _fire(_bot_send(opp_wid[3:],
        f"⚔️ *{me['display_name']}* muốn thách đấu lại!\n\nMở lobby để ghép trận."))
    return jsonify({"ok": True})


# ── B2: Match history ──────────────────────────────────────────────────────────

@app.route("/api/history")
def history():
    wid, _ = auth(request)
    if not wid:
        return jsonify({"error": "Chưa đăng ký"}), 401
    conn = get_db()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT *,
                    CASE WHEN p1_web_id=%s THEN p2_name ELSE p1_name END AS opponent
                FROM matches
                WHERE p1_web_id=%s OR p2_web_id=%s
                ORDER BY matched_at DESC LIMIT 20
            """, (wid, wid, wid))
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify([dict(r) for r in rows])


# ── B3 + C1: Stats & leaderboard ──────────────────────────────────────────────

@app.route("/api/stats")
def stats():
    wid, _ = auth(request)
    if not wid:
        return jsonify({"error": "Chưa đăng ký"}), 401
    conn = get_db()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT COUNT(*) AS total FROM matches
                WHERE p1_web_id=%s OR p2_web_id=%s
            """, (wid, wid))
            total = (cur.fetchone() or {}).get("total", 0)
            cur.execute(
                "SELECT thumbs_up, thumbs_down FROM players WHERE web_id=%s", (wid,)
            )
            p = cur.fetchone() or {}
    finally:
        conn.close()
    return jsonify({
        "total_matches": total,
        "thumbs_up":   p.get("thumbs_up", 0),
        "thumbs_down": p.get("thumbs_down", 0),
    })


@app.route("/api/leaderboard")
def leaderboard():
    conn = get_db()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT name, COUNT(*) AS matches FROM (
                    SELECT p1_name AS name FROM matches
                    UNION ALL
                    SELECT p2_name AS name FROM matches
                ) t
                GROUP BY name ORDER BY matches DESC LIMIT 10
            """)
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify([dict(r) for r in rows])


# ── C2: Rating ─────────────────────────────────────────────────────────────────

@app.route("/api/rate", methods=["POST"])
def rate():
    wid, _ = auth(request)
    if not wid:
        return jsonify({"error": "Chưa đăng ký"}), 401
    d          = request.json or {}
    target_wid = d.get("target_id", "")
    rating     = d.get("rating", "")
    if rating not in ("up", "down") or not target_wid:
        return jsonify({"error": "Invalid"}), 400
    col = "thumbs_up" if rating == "up" else "thumbs_down"
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE players SET {col}={col}+1 WHERE web_id=%s", (target_wid,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    _async(_init_bot())
    port = int(os.environ.get("PORT", 5000))
    print(f"[WEB] Starting on port {port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
