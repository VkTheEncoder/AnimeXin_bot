# main.py

import logging
import io
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    DispatcherHandlerStop,
)
import config
from utils import search_series, get_series_info, get_episode_videos, extract_italian_subtitle

# — Logging setup —
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

    series_map = {}
    buttons = []
    for i, s in enumerate(series_list):
        slug = s.get("slug")
        title = s.get("title") or f"Series {i+1}"
        if not slug:
            continue
        key = str(i)
        series_map[key] = slug
        buttons.append([InlineKeyboardButton(title, callback_data=f"series#{key}")])

    context.user_data["series_map"] = series_map
    update.message.reply_text(
        "Select a series:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


def series_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    key = query.data.split("#", 1)[1]
    slug = context.user_data.get("series_map", {}).get(key)
    if not slug:
        return query.edit_message_text("❌ Invalid series selection.")

    try:
        info = get_series_info(slug)
    except Exception as e:
        logger.error("Series info error: %s", e)
        return query.edit_message_text("⚠️ Could not fetch series info.")

    title = info.get("title") or slug
    episodes = info.get("episodes") or []
    if not isinstance(episodes, list):
        episodes = []

    if not episodes:
        return query.edit_message_text(
            f"No episodes found for **{title}**.",
            parse_mode="Markdown"
        )

    ep_map = {}
    buttons = []
    for i, ep in enumerate(episodes):
        ep_slug = ep.get("ep_slug") or ep.get("slug")
        number = ep.get("episode_number") or ep.get("number") or (i + 1)
        label = ep.get("title") or f"Episode {number}"
        if not ep_slug:
            continue
        key = str(i)
        ep_map[key] = ep_slug
        buttons.append([InlineKeyboardButton(label, callback_data=f"episode#{key}")])

    context.user_data["ep_map"] = ep_map
    query.edit_message_text(
        f"**{title}**\nSelect an episode:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )


def episode_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    key = query.data.split("#", 1)[1]
    ep_slug = context.user_data.get("ep_map", {}).get(key)
    if not ep_slug:
        return query.edit_message_text("❌ Invalid episode selection.")

    try:
        servers = get_episode_videos(ep_slug)
    except Exception as e:
        logger.error("Episode videos error: %s", e)
        return query.edit_message_text("⚠️ Could not fetch episode video links.")

    # Find the Dailymotion server
    selected = next(
        (s for s in servers
         if s["server_name"].lower().startswith("all sub player dailymotion")),
        None
    )
    if not selected:
        return query.edit_message_text(
            "🚫 ‘All Sub Player Dailymotion’ server not available."
        )

    video_url = selected["video_url"]
    subtitle_url = extract_italian_subtitle(video_url)

    # First, send the video link
    query.message.reply_text(
        f"🎬 *Video (Dailymotion)*\n{video_url}",
        parse_mode="Markdown"
    )

    # Then download & send the subtitle as a .srt document
    if subtitle_url:
        try:
            resp = requests.get(subtitle_url)
            resp.raise_for_status()
            buffer = io.BytesIO(resp.content)
            buffer.name = "italian_subtitles.srt"
            query.message.reply_document(
                document=buffer,
                filename="italian_subtitles.srt",
                caption="💬 Here are the Italian subtitles"
            )
        except Exception as e:
            logger.error("Subtitle download error: %s", e)
            query.message.reply_text("⚠️ Failed to download subtitles.")
    else:
        query.message.reply_text("⚠️ Italian subtitles not found.")


def error_handler(update: object, context: CallbackContext):
    logger.error("Update caused error: %s", context.error)
    if update and getattr(update, "message", None):
        update.message.reply_text("😵 Oops, something went wrong.")
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
