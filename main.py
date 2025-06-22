# main.py

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext
)
from telegram.ext import DispatcherHandlerStop
import config
from utils import (
    search_series,
    get_series_info,
    get_episode_videos,
    extract_italian_subtitle,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Welcome to the Animexin bot!\n\n"
        "Use /search <title> to look up a Donghua/Anime."
    )

def search(update: Update, context: CallbackContext):
    if not context.args:
        return update.message.reply_text("Usage: /search <series name>")

    query = " ".join(context.args)
    try:
        series_list = search_series(query)
    except Exception as e:
        logger.error("Search error: %s", e)
        return update.message.reply_text("⚠️ Error contacting animexin_api.")

    if not series_list:
        return update.message.reply_text(f"🚫 No series found for “{query}”.")

    keyboard = [
        [InlineKeyboardButton(item["title"], callback_data=f"series#{item['slug']}")]
        for item in series_list
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select a series:", reply_markup=reply_markup)

def series_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    slug = query.data.split("#", 1)[1]

    try:
        info = get_series_info(slug)
    except Exception as e:
        logger.error("Series info error: %s", e)
        return query.edit_message_text("⚠️ Could not fetch series info.")

    title = info.get("title", slug)
    episodes = info.get("episodes", [])
    if not episodes:
        return query.edit_message_text(f"No episodes found for **{title}**.")

    keyboard = [
        [InlineKeyboardButton(f"Episode {ep['number']}", callback_data=f"episode#{ep['slug']}")]
        for ep in episodes
    ]
    reply = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(
        f"**{title}**\nSelect an episode:",
        reply_markup=reply,
        parse_mode="Markdown"
    )

def episode_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    ep_slug = query.data.split("#", 1)[1]

    try:
        servers = get_episode_videos(ep_slug)
    except Exception as e:
        logger.error("Episode videos error: %s", e)
        return query.edit_message_text("⚠️ Could not fetch episode video links.")

    # Pick only the All Sub Player Dailymotion server
    selected = next(
        (s for s in servers if s["server_name"].lower().startswith("all sub player dailymotion")),
        None
    )
    if not selected:
        return query.edit_message_text("🚫 ‘All Sub Player Dailymotion’ server not available.")

    video_url = selected["video_url"]
    subtitle_url = extract_italian_subtitle(video_url)

    text = f"🎬 *Video (Dailymotion)*\n{video_url}"
    if subtitle_url:
        text += f"\n\n💬 *Italian subtitles*\n{subtitle_url}"
    else:
        text += "\n\n⚠️ Italian subtitles not found."

    query.edit_message_text(text, parse_mode="Markdown")

def error_handler(update: object, context: CallbackContext):
    logger.error("Update caused error: %s", context.error)
    if update and getattr(update, "message", None):
        update.message.reply_text("😵 Oops, something went wrong.")
    # Stop further propagation
    raise DispatcherHandlerStop()

def main():
    updater = Updater(config.TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("search", search))
    dp.add_handler(CallbackQueryHandler(series_callback, pattern=r"^series#"))
    dp.add_handler(CallbackQueryHandler(episode_callback, pattern=r"^episode#"))
    dp.add_error_handler(error_handler)

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
