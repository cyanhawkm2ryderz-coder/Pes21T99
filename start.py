import threading, os

def run_flask():
    from web import app, init_db
    init_db()
    port = int(os.environ.get("PORT", 5000))
    print(f"[WEB] Starting on port {port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)

if __name__ == "__main__":
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    print("[BOT] Starting...", flush=True)
    import database as db
    db.init_db()
    from bot import main as bot_main
    bot_main()
