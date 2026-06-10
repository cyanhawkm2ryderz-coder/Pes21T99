"""
PES Matchmaker Bot
  /register  — đăng ký hồ sơ (chat riêng với bot)
  /ready     — tìm đối trong group
  /cancel    — hủy tìm đối
  /profile   — xem hồ sơ
  /help      — hướng dẫn
"""

import os, sys, logging
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                           ConversationHandler, MessageHandler, filters, ContextTypes)
import database as db

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_URL   = "https://pes21t99.onrender.com"
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)

# Conversation states
ASK_INGAME, ASK_PLATFORM, ASK_TIER, ASK_PARSEC = range(4)

PLATFORMS = ["PS4", "PS5", "PC"]
TIERS     = ["Tier 1", "Tier 2", "Tier 3", "Tier 4", "Tier 5"]

PLATFORM_KB = ReplyKeyboardMarkup([[p] for p in PLATFORMS], one_time_keyboard=True, resize_keyboard=True)
TIER_KB     = ReplyKeyboardMarkup(
    [["Tier 1 ⭐⭐⭐⭐⭐", "Tier 2 ⭐⭐⭐⭐"],
     ["Tier 3 ⭐⭐⭐",    "Tier 4 ⭐⭐"],
     ["Tier 5 ⭐"]],
    one_time_keyboard=True, resize_keyboard=True
)

TIER_STAR = {
    "Tier 1": "⭐⭐⭐⭐⭐",
    "Tier 2": "⭐⭐⭐⭐",
    "Tier 3": "⭐⭐⭐",
    "Tier 4": "⭐⭐",
    "Tier 5": "⭐",
}
PLATFORM_EMOJI = {"PS4": "🎮", "PS5": "🎮", "PC": "💻"}


# ── helpers ───────────────────────────────────────────────────────────────────

def is_group(update): return update.effective_chat.type in ("group", "supergroup")

def player_card(p) -> str:
    stars = TIER_STAR.get(p["tier"], "")
    pe    = PLATFORM_EMOJI.get(p["platform"], "🎮")
    link  = p["parsec_link"] or ""
    lines = [
        f"⚽ *{p['display_name']}* đang tìm đối!",
        f"{pe} {p['platform']}  {stars} {p['tier']}",
        f"🆔 `{p['ingame_name']}`",
    ]
    if link:
        lines.append(f"🔗 Parsec: {link}")
    return "\n".join(lines)

def match_text(searcher, joiner, host, link) -> str:
    se = PLATFORM_EMOJI.get(searcher["platform"], "🎮")
    je = PLATFORM_EMOJI.get(joiner["platform"],  "🎮")
    ss = TIER_STAR.get(searcher["tier"], "")
    js = TIER_STAR.get(joiner["tier"],  "")
    return (
        f"⚔️ *TRẬN ĐẤU BẮT ĐẦU!*\n\n"
        f"{se} *{searcher['display_name']}* {ss}\n"
        f"🆚\n"
        f"{je} *{joiner['display_name']}* {js}\n\n"
        f"🏠 Host: *{host['display_name']}*\n"
        f"🔗 Link Parsec: {link}\n\n"
        f"_🔒 Slot đã khoá_"
    )

def no_link_text(host_name, bot_name) -> str:
    return (
        f"⚠️ *{host_name}* chưa đặt link Parsec!\n\n"
        f"Nhắn `/setlink <link>` cho [@{bot_name}](https://t.me/{bot_name}) rồi thử lại."
    )

def host_choice_kb(searcher_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Host bạn",  callback_data=f"host_them:{searcher_id}"),
        InlineKeyboardButton("🏠 Host tôi",  callback_data=f"host_me:{searcher_id}"),
    ]])


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_name = ctx.bot.username
    if is_group(update):
        await update.message.reply_text(
            f"⚽ *PES Matchmaker* sẵn sàng!\n\n"
            f"Lần đầu: [đăng ký tại đây](https://t.me/{bot_name}?start=go) _(chat riêng với bot)_\n\n"
            f"Sau đó dùng `/ready` trong group để tìm đối!",
            parse_mode="Markdown", disable_web_page_preview=True
        )
    else:
        p = db.get_player(update.effective_user.id)
        if p:
            await update.message.reply_text(
                f"Chào *{p['display_name']}*!\n\nDùng /profile để xem hồ sơ hoặc /register để cập nhật.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "⚽ *PES Matchmaker*\n\nDùng /register để tạo hồ sơ.",
                parse_mode="Markdown"
            )


# ── /register ─────────────────────────────────────────────────────────────────

async def cmd_register(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if is_group(update):
        bot_name = ctx.bot.username
        await update.message.reply_text(
            f"📝 Đăng ký hồ sơ cần thực hiện trong chat riêng.\n"
            f"👉 [Nhấn đây để đăng ký](https://t.me/{bot_name}?start=go)",
            parse_mode="Markdown", disable_web_page_preview=True
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "📝 *Đăng ký hồ sơ PES*\n\nBước 1/4 — Nhập *tên ingame* của bạn:",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    return ASK_INGAME


async def got_ingame(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["ig"] = update.message.text.strip()
    await update.message.reply_text("Bước 2/4 — Chọn *platform*:", parse_mode="Markdown", reply_markup=PLATFORM_KB)
    return ASK_PLATFORM


async def got_platform(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    v = update.message.text.strip()
    if v not in PLATFORMS:
        await update.message.reply_text("Vui lòng chọn từ bàn phím.", reply_markup=PLATFORM_KB)
        return ASK_PLATFORM
    ctx.user_data["pf"] = v
    await update.message.reply_text(
        "Bước 3/4 — Chọn *Tier* của bạn:\n_(T1 cao nhất, T5 mới chơi)_",
        parse_mode="Markdown", reply_markup=TIER_KB
    )
    return ASK_TIER


async def got_tier(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Nhận cả dạng "Tier 1 ⭐⭐⭐⭐⭐" hoặc "Tier 1"
    raw = update.message.text.strip()
    tier = next((t for t in TIERS if raw.startswith(t)), None)
    if not tier:
        await update.message.reply_text("Vui lòng chọn từ bàn phím.", reply_markup=TIER_KB)
        return ASK_TIER
    ctx.user_data["tier"] = tier
    await update.message.reply_text(
        "Bước 4/4 — Nhập *link Parsec* của bạn:\n"
        "_(Ví dụ: `https://parsec.app/...`)_\n\n"
        "Gõ `-` nếu muốn bỏ qua.",
        parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    return ASK_PARSEC


async def got_parsec(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw   = update.message.text.strip()
    link  = "" if raw == "-" else raw
    u     = update.effective_user
    db.upsert_player(
        u.id, u.username or "", u.full_name,
        ctx.user_data["ig"], ctx.user_data["pf"],
        ctx.user_data["tier"], link
    )
    stars = TIER_STAR.get(ctx.user_data["tier"], "")
    await update.message.reply_text(
        f"✅ *Đăng ký thành công!*\n\n"
        f"👤 {u.full_name}\n"
        f"🆔 `{ctx.user_data['ig']}`\n"
        f"{PLATFORM_EMOJI.get(ctx.user_data['pf'], '🎮')} {ctx.user_data['pf']}  "
        f"{stars} {ctx.user_data['tier']}\n"
        f"🔗 {link or '_(chưa đặt)_'}\n\n"
        f"Quay về group và gõ `/ready` để tìm đối!",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Đã hủy.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ── /setlink ──────────────────────────────────────────────────────────────────

async def cmd_setlink(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    p = db.get_player(update.effective_user.id)
    if not p:
        await update.message.reply_text("Dùng /register trước.")
        return
    if not ctx.args:
        cur = p["parsec_link"] or "_(chưa đặt)_"
        await update.message.reply_text(
            f"Link Parsec hiện tại: {cur}\n\nĐể đổi: `/setlink <link>`",
            parse_mode="Markdown"
        )
        return
    db.get_conn()  # ensure open
    with db.get_conn() as conn:
        conn.execute("UPDATE players SET parsec_link=? WHERE user_id=?",
                     (ctx.args[0].strip(), update.effective_user.id))
    await update.message.reply_text(f"✅ Đã lưu: `{ctx.args[0].strip()}`", parse_mode="Markdown")


# ── /profile ──────────────────────────────────────────────────────────────────

async def cmd_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    p = db.get_player(update.effective_user.id)
    if not p:
        bot_name = ctx.bot.username
        await update.message.reply_text(
            f"Chưa đăng ký. 👉 [Đăng ký tại đây](https://t.me/{bot_name}?start=go)",
            parse_mode="Markdown", disable_web_page_preview=True
        )
        return
    stars  = TIER_STAR.get(p["tier"], "")
    pe     = PLATFORM_EMOJI.get(p["platform"], "🎮")
    status = "🟢 Đang tìm trận" if p["is_ready"] else "🔴 Không rảnh"
    link   = p["parsec_link"] or "_(chưa đặt — dùng /setlink)_"
    await update.message.reply_text(
        f"👤 *{p['display_name']}* — {status}\n"
        f"🆔 `{p['ingame_name']}`\n"
        f"{pe} {p['platform']}  {stars} {p['tier']}\n"
        f"🔗 {link}",
        parse_mode="Markdown"
    )


# ── /ready ────────────────────────────────────────────────────────────────────

async def cmd_ready(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    p   = db.get_player(uid)
    if not p:
        bot_name = ctx.bot.username
        await update.message.reply_text(
            f"Chưa đăng ký. 👉 [Nhấn đây](https://t.me/{bot_name}?start=go)",
            parse_mode="Markdown", disable_web_page_preview=True
        )
        return
    if p["is_ready"]:
        await update.message.reply_text("Bạn đang trong hàng chờ rồi. Dùng /cancel để rút.")
        return

    sent = await update.message.reply_text(
        player_card(p),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=host_choice_kb(uid)
    )
    db.set_ready(uid, True, chat_id=update.effective_chat.id, msg_id=sent.message_id)


# ── /cancel ───────────────────────────────────────────────────────────────────

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    p   = db.get_player(uid)
    if not p or not p["is_ready"]:
        await update.message.reply_text("Bạn không có lượt tìm đối nào đang mở.")
        return
    # Edit card cũ
    if p["ready_chat"] and p["ready_msg"]:
        try:
            await ctx.bot.edit_message_text(
                chat_id=p["ready_chat"], message_id=p["ready_msg"],
                text=f"🚫 *{p['display_name']}* đã hủy tìm đối.",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    db.set_ready(uid, False)
    await update.message.reply_text("🔴 Đã hủy tìm đối.")


# ── Callback: Host bạn ────────────────────────────────────────────────────────

async def cb_host_them(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Người tìm đối sẽ host — hiện link Parsec của họ."""
    query       = update.callback_query
    searcher_id = int(query.data.split(":")[1])
    joiner      = update.effective_user

    searcher = db.get_player(searcher_id)
    jp       = db.get_player(joiner.id)

    if not searcher or not searcher["is_ready"]:
        await query.answer("Slot này đã bị khoá hoặc không còn hiệu lực!", show_alert=True)
        return
    if joiner.id == searcher_id:
        await query.answer("Không thể tự ghép với chính mình 😅", show_alert=True)
        return
    if not jp:
        bot_name = ctx.bot.username
        await query.answer(f"Bạn chưa đăng ký! Nhắn /start cho @{bot_name}", show_alert=True)
        return

    link = searcher["parsec_link"]
    if not link:
        await query.answer("", show_alert=False)
        await query.edit_message_text(
            no_link_text(searcher["display_name"], ctx.bot.username),
            parse_mode="Markdown", disable_web_page_preview=True
        )
        return

    # Khoá slot
    db.set_ready(searcher_id, False)

    await query.edit_message_text(
        match_text(searcher, jp, host=searcher, link=link),
        parse_mode="Markdown", disable_web_page_preview=True
    )

    # Ping riêng cho searcher
    try:
        je = PLATFORM_EMOJI.get(jp["platform"], "🎮")
        js = TIER_STAR.get(jp["tier"], "")
        await ctx.bot.send_message(
            chat_id=searcher_id,
            text=(
                f"⚔️ *{jp['display_name']}* vừa nhảy vào đá với bạn!\n"
                f"{je} {jp['platform']}  {js} {jp['tier']}\n"
                f"🆔 `{jp['ingame_name']}`\n\n"
                f"Bạn đang host — chờ họ vào Parsec nhé!"
            ),
            parse_mode="Markdown"
        )
    except Exception:
        pass


# ── Callback: Host tôi ────────────────────────────────────────────────────────

async def cb_host_me(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Người bấm sẽ host — hiện link Parsec của họ và tag người tìm đối."""
    query       = update.callback_query
    searcher_id = int(query.data.split(":")[1])
    joiner      = update.effective_user

    searcher = db.get_player(searcher_id)
    jp       = db.get_player(joiner.id)

    if not searcher or not searcher["is_ready"]:
        await query.answer("Slot này đã bị khoá hoặc không còn hiệu lực!", show_alert=True)
        return
    if joiner.id == searcher_id:
        await query.answer("Không thể tự ghép với chính mình 😅", show_alert=True)
        return
    if not jp:
        bot_name = ctx.bot.username
        await query.answer(f"Bạn chưa đăng ký! Nhắn /start cho @{bot_name}", show_alert=True)
        return

    link = jp["parsec_link"]
    if not link:
        await query.answer("", show_alert=False)
        await query.edit_message_text(
            no_link_text(jp["display_name"], ctx.bot.username),
            parse_mode="Markdown", disable_web_page_preview=True
        )
        return

    # Khoá slot
    db.set_ready(searcher_id, False)

    # Tag searcher trong group để họ thấy link
    searcher_tag = f"@{searcher['username']}" if searcher["username"] else searcher["display_name"]

    await query.edit_message_text(
        match_text(searcher, jp, host=jp, link=link) +
        f"\n\n👆 {searcher_tag} nhấn link trên để vào!",
        parse_mode="Markdown", disable_web_page_preview=True
    )

    # Ping riêng cho searcher kèm link
    try:
        await ctx.bot.send_message(
            chat_id=searcher_id,
            text=(
                f"⚔️ *{jp['display_name']}* sẽ host cho bạn!\n\n"
                f"🔗 *Link Parsec:* {link}\n\n"
                f"Nhấn vào link để join trận!"
            ),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception:
        pass


# ── /lobby ───────────────────────────────────────────────────────────────────

async def cmd_lobby(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 Mở Lobby", web_app=WebAppInfo(url=WEB_URL))
    ]])
    await update.message.reply_text("⚽ Bấm để vào sảnh tìm đối:", reply_markup=kb)


# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bot_name = ctx.bot.username
    await update.message.reply_text(
        "📖 *Hướng dẫn*\n\n"
        f"1️⃣ Chat riêng [@{bot_name}](https://t.me/{bot_name}) → `/register`\n"
        f"   _(điền tên ingame, platform, tier, link Parsec)_\n\n"
        "2️⃣ Vào group gõ `/ready` → bot đăng card tìm đối\n\n"
        "3️⃣ Đối thủ thấy card → chọn:\n"
        "   🏠 *Host bạn* — bạn host, link của bạn hiện ra\n"
        "   🏠 *Host tôi* — đối thủ host, link của họ hiện ra\n\n"
        "Card tự khoá khi đã có đôi.\n\n"
        "*Lệnh khác:*\n"
        "`/cancel` — hủy tìm đối\n"
        "`/setlink <link>` — cập nhật link Parsec\n"
        "`/profile` — xem hồ sơ",
        parse_mode="Markdown", disable_web_page_preview=True
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    db.init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("register", cmd_register)],
        states={
            ASK_INGAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_ingame)],
            ASK_PLATFORM: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_platform)],
            ASK_TIER:     [MessageHandler(filters.TEXT & ~filters.COMMAND, got_tier)],
            ASK_PARSEC:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_parsec)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("lobby",   cmd_lobby))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("setlink", cmd_setlink))
    app.add_handler(CommandHandler("ready",   cmd_ready))
    app.add_handler(CommandHandler("cancel",  cmd_cancel))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CallbackQueryHandler(cb_host_them, pattern=r"^host_them:\d+$"))
    app.add_handler(CallbackQueryHandler(cb_host_me,   pattern=r"^host_me:\d+$"))

    print("Bot dang chay...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
