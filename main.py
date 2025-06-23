# main.py
import logging
import io
from urllib.parse import urlparse
import requests
import os
import tempfile
import subprocess

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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Welcome! Use /search <title> to begin.")


def search(update: Update, context: CallbackContext):
    if not context.args:
        return update.message.reply_text("Usage: /search <series name>")

    query = " ".join(context.args)
    try:
        lst = search_series(query)
    except Exception as e:
        logger.error("Search error: %s", e)
        return update.message.reply_text("⚠️ API error.")

    if not lst:
        return update.message.reply_text(f"No results for “{query}.”")

    series_map, buttons = {}, []
    for i, s in enumerate(lst):
        slug = s.get("slug")
        title = s.get("title") or f"Series {i+1}"
        if not slug:
            continue
        series_map[str(i)] = slug
        buttons.append([InlineKeyboardButton(title, callback_data=f"series#{i}")])

    context.user_data["series_map"] = series_map
    update.message.reply_text("Select a series:", reply_markup=InlineKeyboardMarkup(buttons))


def series_callback(update: Update, context: CallbackContext):
    q = update.callback_query; q.answer()
    key = q.data.split("#", 1)[1]
    slug = context.user_data.get("series_map", {}).get(key)
    if not slug:
        return q.edit_message_text("❌ Invalid selection.")

    try:
        info = get_series_info(slug)
    except Exception as e:
        logger.error("Series info error: %s", e)
        return q.edit_message_text("⚠️ Failed to fetch info.")

    title = info.get("title") or slug
    eps = info.get("episodes") or []
    if not isinstance(eps, list):
        eps = []

    if not eps:
        return q.edit_message_text(f"No episodes for **{title}**.", parse_mode="Markdown")

    ep_map, buttons = {}, []
    for i, ep in enumerate(eps):
        eslug = ep.get("ep_slug")
        num   = ep.get("episode_number") or (i + 1)
        label = ep.get("title") or f"Episode {num}"
        if not eslug:
            continue
        ep_map[str(i)] = eslug
        buttons.append([InlineKeyboardButton(label, callback_data=f"episode#{i}")])

    context.user_data["ep_map"] = ep_map
    q.edit_message_text(
        f"**{title}**\nSelect an episode:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )


def episode_callback(update: Update, context: CallbackContext):
    q = update.callback_query; q.answer()
    key = q.data.split("#", 1)[1]
    ep_slug = context.user_data.get("ep_map", {}).get(key)
    if not ep_slug:
        return q.edit_message_text("❌ Invalid selection.")

    try:
        servers = get_episode_videos(ep_slug)
    except Exception as e:
        logger.error("Episode videos error: %s", e)
        return q.edit_message_text("⚠️ Failed to fetch videos.")

    sel = next(
        (s for s in servers
         if s["server_name"].lower().startswith("all sub player dailymotion")),
        None
    )
    if not sel:
        return q.edit_message_text("🚫 Dailymotion server not available.")

    video_url = sel.get("video_url")
    wrapper   = sel.get("embed_url") or sel.get("iframe_src") or video_url

    # 1) Playback link
    q.message.reply_text(f"🎬 Video (Dailymotion)\n{video_url}")

    # 2) Fetch subtitles via yt-dlp
    data = download_subtitles_with_ytdlp(video_url, lang="it")
    if not data:
        return q.message.reply_text("⚠️ Italian subtitles not found via yt-dlp.")

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
    dp.add_handler(CallbackQueryHandler(series_callback, pattern=r"^series#"))
    dp.add_handler(CallbackQueryHandler(episode_callback, pattern=r"^episode#"))
    dp.add_error_handler(error_handler)

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
