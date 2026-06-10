import threading, os, asyncio, traceback

def start_bot():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        from bot import main as bot_main
        print("[BOT] Starting...", flush=True)
        bot_main()
    except Exception as e:
        print(f"[BOT ERROR] {e}", flush=True)
        traceback.print_exc()

if __name__ == "__main__":
    from web import app as flask_app, init_db as web_init
    web_init()

    t = threading.Thread(target=start_bot, daemon=True)
    t.start()

    port = int(os.environ.get("PORT", 5000))
    print(f"[WEB] Starting on port {port}", flush=True)
    flask_app.run(host="0.0.0.0", port=port, debug=False)
