import os
import random
import logging
from datetime import datetime, timedelta

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ---------- CONFIG ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Set in Railway variables
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY", "")  # Optional
FOOTBALL_API_URL = "https://v3.football.api-sports.io/fixtures"

BOT_NAME = "SB24 Lucky23"
BOT_EMOJI = "🍀"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------- IN-MEMORY STORAGE ----------
checkin_data = {}       # user_id -> last checkin datetime
user_points = {}        # user_id -> points
giveaway_entries = []   # list of user_ids in current draw
giveaway_active = False

# ---------- START ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("⚽ Football Updates", callback_data="football")],
        [InlineKeyboardButton("🎁 Join Giveaway", callback_data="giveaway_join")],
        [InlineKeyboardButton("✅ Daily Check-in", callback_data="checkin")],
        [InlineKeyboardButton("💎 My Points", callback_data="points")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        f"👋 Hello <b>{user.first_name}</b>!\n\n"
        f"Welcome to <b>{BOT_NAME}</b> {BOT_EMOJI}⚽🎁\n\n"
        "Here's what I can do:\n"
        "• ⚽ <b>Football Updates</b> — Live scores & fixtures\n"
        "• 🎁 <b>Lucky Draw</b> — Join community giveaways\n"
        "• ✅ <b>Daily Check-in</b> — Earn points every day\n"
        "• 💎 <b>Points</b> — Track your rewards\n\n"
        "Use the buttons below or type /help."
    )
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

# ---------- HELP ----------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>Available Commands</b>\n\n"
        "/start – Main menu\n"
        "/football – Today's football fixtures\n"
        "/live – Live matches right now\n"
        "/giveaway – Join the current giveaway\n"
        "/checkin – Claim your daily reward\n"
        "/points – See your points balance\n"
        "/help – Show this message"
    )
    await update.message.reply_text(text, parse_mode="HTML")

# ---------- FOOTBALL ----------
def fetch_fixtures(live_only=False):
    if not FOOTBALL_API_KEY:
        return None
    headers = {"x-apisports-key": FOOTBALL_API_KEY}
    params = {"live": "all"} if live_only else {"date": datetime.utcnow().strftime("%Y-%m-%d")}
    try:
        r = requests.get(FOOTBALL_API_URL, headers=headers, params=params, timeout=10)
        data = r.json()
        return data.get("response", [])
    except Exception as e:
        logger.error(f"Football API error: {e}")
        return None


def format_fixtures(fixtures, live_only=False):
    if fixtures is None:
        return "⚠️ Football data is temporarily unavailable. Please try again later."
    if not fixtures:
        return "📭 No matches found right now."

    lines = ["⚽ <b>Live Matches</b>\n" if live_only else "⚽ <b>Today's Fixtures</b>\n"]

    for f in fixtures[:10]:
        home = f["teams"]["home"]["name"]
        away = f["teams"]["away"]["name"]
        goals_home = f["goals"]["home"]
        goals_away = f["goals"]["away"]
        status = f["fixture"]["status"]["short"]
        league = f["league"]["name"]

        if live_only or status in ("1H", "2H", "HT", "ET", "P"):
            score = f"{goals_home or 0} - {goals_away or 0}"
        else:
            score = "vs"

        lines.append(f"🏆 {league}\n   {home}  <b>{score}</b>  {away}\n")

    return "\n".join(lines)


async def football(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Fetching today's fixtures...")
    fixtures = fetch_fixtures(live_only=False)
    text = format_fixtures(fixtures)
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def live(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Fetching live matches...")
    fixtures = fetch_fixtures(live_only=True)
    text = format_fixtures(fixtures, live_only=True)
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


# ---------- LUCKY DRAW ----------
async def giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not giveaway_active:
        await update.message.reply_text(
            "🎁 There is no active giveaway right now.\nStay tuned!"
        )
        return
    await join_giveaway(update, context)


async def join_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not giveaway_active:
        msg = "❌ No giveaway is currently running."
    elif user_id in giveaway_entries:
        msg = "✅ You're already in the draw! Good luck 🍀"
    else:
        giveaway_entries.append(user_id)
        msg = f"🎉 You joined the giveaway! Total entries: {len(giveaway_entries)}"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg)
    else:
        await update.message.reply_text(msg)


async def start_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global giveaway_active, giveaway_entries
    admin_ids = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("⛔ You are not authorized to run giveaways.")
        return

    giveaway_active = True
    giveaway_entries = []
    await update.message.reply_text(
        f"🎉 A new giveaway has started on <b>{BOT_NAME}</b>!\nUsers can now /giveaway to join.",
        parse_mode="HTML",
    )


async def end_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global giveaway_active, giveaway_entries
    admin_ids = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("⛔ You are not authorized.")
        return

    if not giveaway_entries:
        await update.message.reply_text("❌ No participants in the giveaway.")
        giveaway_active = False
        return

    winner_id = random.choice(giveaway_entries)
    try:
        winner = await context.bot.get_chat(winner_id)
        winner_name = winner.first_name
    except Exception:
        winner_name = f"User {winner_id}"

    await update.message.reply_text(
        f"🏆 <b>Giveaway Winner!</b>\n\nCongratulations <b>{winner_name}</b>! 🎉\n"
        f"Total entries: {len(giveaway_entries)}",
        parse_mode="HTML",
    )

    giveaway_active = False
    giveaway_entries = []


# ---------- DAILY CHECK-IN ----------
async def checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = datetime.utcnow()

    last = checkin_data.get(user_id)
    if last and now - last < timedelta(hours=24):
        remaining = timedelta(hours=24) - (now - last)
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes = remainder // 60
        msg = f"⏳ You already checked in today!\nCome back in <b>{hours}h {minutes}m</b>."
    else:
        checkin_data[user_id] = now
        reward = random.randint(5, 15)
        user_points[user_id] = user_points.get(user_id, 0) + reward
        msg = (
            f"✅ <b>Check-in successful!</b>\n\n"
            f"You earned <b>{reward} points</b> 🎉\n"
            f"Your total: <b>{user_points[user_id]} points</b>"
        )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg, parse_mode="HTML")
    else:
        await update.message.reply_text(msg, parse_mode="HTML")


async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    total = user_points.get(user_id, 0)
    msg = f"💎 You have <b>{total} points</b>."

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg, parse_mode="HTML")
    else:
        await update.message.reply_text(msg, parse_mode="HTML")


# ---------- CALLBACK ROUTER ----------
async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "football":
        await query.answer()
        fixtures = fetch_fixtures(live_only=False)
        text = format_fixtures(fixtures)
        await query.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)
    elif data == "giveaway_join":
        await join_giveaway(update, context)
    elif data == "checkin":
        await checkin(update, context)
    elif data == "points":
        await points(update, context)


# ---------- MAIN ----------
def main():
    if not BOT_TOKEN:
        raise SystemExit("❌ BOT_TOKEN environment variable is not set!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("football", football))
    app.add_handler(CommandHandler("live", live))
    app.add_handler(CommandHandler("giveaway", giveaway))
    app.add_handler(CommandHandler("startgiveaway", start_giveaway))
    app.add_handler(CommandHandler("endgiveaway", end_giveaway))
    app.add_handler(CommandHandler("checkin", checkin))
    app.add_handler(CommandHandler("points", points))
    app.add_handler(CallbackQueryHandler(button_router))

    logger.info(f"🤖 {BOT_NAME} bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
