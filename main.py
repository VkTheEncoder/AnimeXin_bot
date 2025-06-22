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

# ——— Logging —————————————————————————————————————————————————————
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ——— Helpers ————————————————————————————————————————————————————
def find_episodes(obj) -> list:
    """
    Recursively search for the first list under the key 'episodes'
    anywhere in a nested dict/list structure.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() == "episodes" and isinstance(v, list):
                return v
            elif isinstance(v, (dict, list)):
                res = find_episodes(v)
                if res:
                    return res
    elif isinstance(obj, list):
        for item in obj:
            res = find_episodes(item)
            if res:
                return res
    return []


# ——— Command Handlers ——————————————————————————————————————————
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
        results = search_series(query)
    except Exception as e:
        logger.error("Search error: %s", e)
        return update.message.reply_text("⚠️ Could not reach animexin_api.")

    if not results:
        return update.message.reply_text(f"🚫 No series found for “{query}”.")

    # Build map of index → slug
    series_map = {}
    buttons = []
    for i, s in enumerate(results):
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

    # Recursively find 'episodes'
    episodes = find_episodes(info)
    title = info.get("title") or slug

    if not episodes:
        logger.info("Payload keys: %s", list(info.keys()))
        return query.edit_message_text(
            f"No episodes found for **{title}**.",
            parse_mode="Markdown"
        )

    # Build episode map
    ep_map = {}
    buttons = []
    for i, ep in enumerate(episodes):
        epi_slug = ep.get("slug")
        num = ep.get("number") or i + 1
        label = ep.get("title") or f"Episode {num}"
        if not epi_slug:
            continue
        key = str(i)
        ep_map[key] = epi_slug
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
        return query.edit_message_text("⚠️ Could not fetch video links.")

    # Filter for our target server
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
    sub_url = extract_italian_subtitle(video_url)

    msg = f"🎬 *Video (Dailymotion)*\n{video_url}"
    if sub_url:
        msg += f"\n\n💬 *Italian subtitles*\n{sub_url}"
    else:
        msg += "\n\n⚠️ Italian subtitles not found."

    query.edit_message_text(msg, parse_mode="Markdown")


def error_handler(update: object, context: CallbackContext):
    logger.error("Update caused error: %s", context.error)
    if update and getattr(update, "message", None):
        update.message.reply_text("😵 Something went wrong.")
    raise DispatcherHandlerStop()


# ——— Bot Startup —————————————————————————————————————————————
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
