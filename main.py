# main.py

import logging
import io
import requests
from urllib.parse import urlparse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    DispatcherHandlerStop,
)
import config
from utils import (
    search_series,
    get_series_info,
    get_episode_videos,
    extract_italian_subtitle_url,
    download_subtitles_with_ytdlp,
)

# — Logging setup —
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 Welcome to the Animexin bot!\n"
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

    # Build a map: index → slug, and stash full list
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

    context.user_data["series_list"] = series_list
    context.user_data["series_map"]  = series_map

    update.message.reply_text(
        "Select a series:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


def series_select_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    key = q.data.split("#", 1)[1]
    series_map = context.user_data.get("series_map", {})
    slug = series_map.get(key)
    if not slug:
        return q.edit_message_text("❌ Invalid selection.")

    try:
        info = get_series_info(slug)
    except Exception as e:
        logger.error("Series info error: %s", e)
        return q.edit_message_text("⚠️ Could not fetch series info.")

    title = info.get("title") or slug
    eps = info.get("episodes") or []
    if not isinstance(eps, list):
        eps = []

    if not eps:
        return q.edit_message_text(f"No episodes for **{title}**.", parse_mode="Markdown")

    # Build episode map
    ep_map = {}
    buttons = []
    for i, ep in enumerate(eps):
        ep_slug = ep.get("ep_slug")
        num     = ep.get("episode_number") or (i + 1)
        label   = ep.get("title") or f"Episode {num}"
        if not ep_slug:
            continue
        key = str(i)
        ep_map[key] = ep_slug
        buttons.append([InlineKeyboardButton(label, callback_data=f"episode#{key}")])

    # Add a Back button
    buttons.append([InlineKeyboardButton("« Back", callback_data="back_to_series")])

    context.user_data["ep_map"] = ep_map

    q.edit_message_text(
        f"**{title}**\nSelect an episode:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )


def back_to_series_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()

    series_list = context.user_data.get("series_list", [])
    series_map  = context.user_data.get("series_map", {})

    if not series_list:
        return q.edit_message_text("⚠️ No previous search to go back to.")

    buttons = []
    for i, s in enumerate(series_list):
        key = str(i)
        title = s.get("title") or f"Series {i+1}"
        buttons.append([InlineKeyboardButton(title, callback_data=f"series#{key}")])

    q.edit_message_text(
        "Select a series:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


def episode_callback(update: Update, context: CallbackContext):
    q = update.callback_query
    q.answer()
    key = q.data.split("#", 1)[1]
    ep_map = context.user_data.get("ep_map", {})
    ep_slug = ep_map.get(key)
    if not ep_slug:
        return q.edit_message_text("❌ Invalid selection.")

    try:
        servers = get_episode_videos(ep_slug)
    except Exception as e:
        logger.error("Episode videos error: %s", e)
        return q.edit_message_text("⚠️ Could not fetch episode video links.")

    # Filter for the All Sub Player Dailymotion server
    selected = next(
        (s for s in servers
         if s["server_name"].lower().startswith("all sub player dailymotion")),
        None
    )
    if not selected:
        return q.edit_message_text("🚫 Dailymotion server not available.")

    video_url = selected["video_url"]
    wrapper   = selected.get("embed_url") or selected.get("iframe_src") or video_url

    # 1) Send the video link
    q.message.reply_text(f"🎬 Video (Dailymotion)\n{video_url}")

    # 2) Download subtitles via yt-dlp fallback
    data = download_subtitles_with_ytdlp(video_url, lang="it")
    if not data:
        return q.message.reply_text("⚠️ Italian subtitles not found.")

    buf = io.BytesIO(data)
    buf.name = "italian_subtitles.srt"
    q.message.reply_document(
        document=buf,
        filename="italian_subtitles.srt",
        caption="💬 Italian subtitles"
    )


def error_handler(update: object, context: CallbackContext):
    logger.error("Unhandled error", exc_info=context.error)
    if update and getattr(update, "message", None):
        update.message.reply_text("😵 Something went wrong.")
    raise DispatcherHandlerStop()


def main():
    updater = Updater(config.TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("search", search))
    dp.add_handler(CallbackQueryHandler(back_to_series_callback, pattern=r"^back_to_series$"))
    dp.add_handler(CallbackQueryHandler(series_select_callback, pattern=r"^series#"))
    dp.add_handler(CallbackQueryHandler(episode_callback, pattern=r"^episode#"))
    dp.add_error_handler(error_handler)

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
