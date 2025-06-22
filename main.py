# main.py

import logging
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

    # Build a map: index -> slug
    series_map = {}
    keyboard = []
    for idx, item in enumerate(series_list):
        slug = item.get("slug")
        title = item.get("title") or slug or f"Series {idx+1}"
        if not slug:
            continue
        key = str(idx)
        series_map[key] = slug
        keyboard.append([InlineKeyboardButton(title, callback_data=f"series#{key}")])

    context.user_data["series_map"] = series_map
    update.message.reply_text(
        "Select a series:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


def series_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    key = query.data.split("#", 1)[1]
    series_map = context.user_data.get("series_map", {})
    slug = series_map.get(key)
    if not slug:
        return query.edit_message_text("❌ Invalid selection.")

    try:
        info = get_series_info(slug)
    except Exception as e:
        logger.error("Series info error: %s", e)
        return query.edit_message_text("⚠️ Could not fetch series info.")

    # Normalize the payload: some responses wrap everything under "data"
    payload = info.get("data") if isinstance(info.get("data"), dict) else info

    title = payload.get("title", slug)
    episodes = payload.get("episodes")
    # Sometimes the API might nest episodes under another key
    if episodes is None:
        # e.g. data.get("data") or data.get("eps")
        episodes = payload.get("data") if isinstance(payload.get("data"), list) else []
    if not isinstance(episodes, list):
        episodes = []

    if not episodes:
        logger.info("No episodes key found in payload; keys were: %s", payload.keys())
        return query.edit_message_text(
            f"No episodes found for **{title}**.",
            parse_mode="Markdown"
        )

    # Build episode map
    ep_map = {}
    keyboard = []
    for idx, ep in enumerate(episodes):
        ep_slug = ep.get("slug")
        number = ep.get("number") or idx + 1
        btn_text = ep.get("title") or f"Episode {number}"
        if not ep_slug:
            continue
        key = str(idx)
        ep_map[key] = ep_slug
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"episode#{key}")])

    context.user_data["ep_map"] = ep_map
    query.edit_message_text(
        f"**{title}**\nSelect an episode:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


def episode_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    key = query.data.split("#", 1)[1]
    ep_map = context.user_data.get("ep_map", {})
    ep_slug = ep_map.get(key)
    if not ep_slug:
        return query.edit_message_text("❌ Invalid episode selection.")

    try:
        servers = get_episode_videos(ep_slug)
    except Exception as e:
        logger.error("Episode videos error: %s", e)
        return query.edit_message_text("⚠️ Could not fetch episode video links.")

    # Pick only the All Sub Player Dailymotion server
    selected = next(
        (s for s in servers if
            s["server_name"].lower().startswith("all sub player dailymotion")),
        None
    )
    if not selected:
        return query.edit_message_text(
            "🚫 ‘All Sub Player Dailymotion’ server not available."
        )

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
