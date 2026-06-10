import sqlite3

DB_FILE = "pes_bot.db"


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS players (
                user_id      INTEGER PRIMARY KEY,
                username     TEXT DEFAULT '',
                display_name TEXT NOT NULL,
                ingame_name  TEXT NOT NULL,
                platform     TEXT NOT NULL,
                tier         TEXT NOT NULL,
                parsec_link  TEXT DEFAULT '',
                is_ready     INTEGER DEFAULT 0,
                ready_chat   INTEGER,
                ready_msg    INTEGER
            );
        """)
        # Migrate: thêm cột nếu DB cũ chưa có
        existing = {r[1] for r in conn.execute("PRAGMA table_info(players)")}
        migrations = [
            ("tier",        "TEXT NOT NULL DEFAULT 'T3'"),
            ("parsec_link", "TEXT DEFAULT ''"),
            ("ready_chat",  "INTEGER"),
            ("ready_msg",   "INTEGER"),
        ]
        for col, defn in migrations:
            if col not in existing:
                conn.execute(f"ALTER TABLE players ADD COLUMN {col} {defn}")


def upsert_player(user_id, username, display_name, ingame_name, platform, tier, parsec_link):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO players (user_id, username, display_name, ingame_name, platform, tier, parsec_link)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                display_name=excluded.display_name,
                ingame_name=excluded.ingame_name,
                platform=excluded.platform,
                tier=excluded.tier,
                parsec_link=excluded.parsec_link
        """, (user_id, username, display_name, ingame_name, platform, tier, parsec_link))


def get_player(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM players WHERE user_id=?", (user_id,)).fetchone()


def set_ready(user_id, ready, chat_id=None, msg_id=None):
    with get_conn() as conn:
        if ready:
            conn.execute(
                "UPDATE players SET is_ready=1, ready_chat=?, ready_msg=? WHERE user_id=?",
                (chat_id, msg_id, user_id)
            )
        else:
            conn.execute(
                "UPDATE players SET is_ready=0, ready_chat=NULL, ready_msg=NULL WHERE user_id=?",
                (user_id,)
            )
