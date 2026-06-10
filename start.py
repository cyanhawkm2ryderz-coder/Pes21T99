import threading, os, traceback, time

def start_bot():
    while True:
        try:
            print("[BOT] Starting...", flush=True)
            import database as db
            db.init_db()
            from bot import main as bot_main
            bot_main()
            print("[BOT] Exited normally", flush=True)
        except Exception as e:
            print(f"[BOT CRASHED] {e}", flush=True)
            traceback.print_exc()
        print("[BOT] Restarting in 5s...", flush=True)
        time.sleep(5)

if __name__ == "__main__":
    t = threading.Thread(target=start_bot, daemon=True)
    t.start()

    from web import app, init_db
    init_db()
    port = int(os.environ.get("PORT", 5000))
    print(f"[WEB] Starting on port {port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
