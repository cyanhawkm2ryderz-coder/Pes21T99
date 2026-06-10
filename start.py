import subprocess, sys, os

if __name__ == "__main__":
    print("[START] Launching bot process...", flush=True)
    bot_proc = subprocess.Popen(
        [sys.executable, "bot.py"],
        stdout=sys.stdout,
        stderr=sys.stderr
    )

    print("[START] Launching web server...", flush=True)
    from web import app, init_db
    init_db()
    port = int(os.environ.get("PORT", 5000))
    try:
        app.run(host="0.0.0.0", port=port, debug=False)
    finally:
        bot_proc.terminate()
