import threading, os
from web import app as flask_app, init_db as web_init

def start_bot():
    from bot import main as bot_main
    bot_main()

if __name__ == "__main__":
    web_init()
    t = threading.Thread(target=start_bot, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port, debug=False)
