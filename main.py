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
        series_list = search_series(query)
    except Exception as e:
        logger.error("Search error: %s", e)
        return update.message.reply_text("⚠️ API error.")

    if not series_list:
        return update.message.reply_text(f"No results for “{query}.”")

    series_map = {}
    buttons = []
    for i, s in enumerate(series_list):
        slug = s.get("slug")
        title = s.get("title") or f"Series {i+1}"
        if not slug:
            continue
        series_map[str(i)] = slug
        buttons.append([InlineKeyboardButton(title, callback_data=f"series#{i}")])

    context.user_data["series_map"] = series_map
    update.message.reply_text("Select a series:", reply_markup=InlineKeyboardMarkup(buttons))


def series_callback(update: Update, context: CallbackContext):
    query = update.callback_query; query.answer()
    key = query.data.split("#", 1)[1]
    slug = context.user_data.get("series_map", {}).get(key)
    if not slug:
        return query.edit_message_text("❌ Invalid selection.")

    try:
        info = get_series_info(slug)
    except Exception as e:
        logger.error("Series info error: %s", e)
        return query.edit_message_text("⚠️ Failed to fetch info.")

    title = info.get("title") or slug
    eps = info.get("episodes") or []
    if not isinstance(eps, list):
        eps = []

    if not eps:
        return query.edit_message_text(f"No episodes for **{title}**.", parse_mode="Markdown")

    ep_map, buttons = {}, []
    for i, ep in enumerate(eps):
        ep_slug = ep.get("ep_slug")
        num = ep.get("episode_number") or (i + 1)
        label = ep.get("title") or f"Episode {num}"
        if not ep_slug:
            continue
        ep_map[str(i)] = ep_slug
        buttons.append([InlineKeyboardButton(label, callback_data=f"episode#{i}")])

    context.user_data["ep_map"] = ep_map
    query.edit_message_text(
        f"**{title}**\nSelect an episode:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


def episode_callback(update: Update, context: CallbackContext):
    query = update.callback_query; query.answer()
    key = query.data.split("#", 1)[1]
    ep_slug = context.user_data.get("ep_map", {}).get(key)
    if not ep_slug:
        return query.edit_message_text("❌ Invalid selection.")

    try:
        servers = get_episode_videos(ep_slug)
    except Exception as e:
        logger.error("Episode videos error: %s", e)
        return query.edit_message_text("⚠️ Failed to fetch videos.")

    selected = next(
        (s for s in servers
         if s["server_name"].lower().startswith("all sub player dailymotion")),
        None
    )
    if not selected:
        return query.edit_message_text("🚫 Dailymotion server not available.")

    video_url = selected["video_url"]
    wrapper = selected.get("embed_url") or selected.get("iframe_src") or video_url

    # 1) send the playback link
    query.message.reply_text(f"🎬 Video (Dailymotion)\n{video_url}")

    # 2) fetch the Italian subtitle URL (always .srt)
    sub_url = extract_italian_subtitle_url(wrapper)
    if not sub_url:
        return query.message.reply_text("⚠️ Italian subtitles not found.")

    try:
        r = requests.get(sub_url)
        r.raise_for_status()
        data = r.content

        # If it’s a VTT, convert quickly 
        if sub_url.lower().endswith((".vtt", ".webvtt")):
            lines = r.text.splitlines()
            blocks, idx, i = [], 1, 0
            while i < len(lines):
                line = lines[i].strip()
                if "-->" in line:
                    start, end = line.split(" --> ")
                    start, end = start.replace(".", ","), end.replace(".", ",")
                    i += 1
                    text_lines = []
                    while i < len(lines) and lines[i].strip():
                        text_lines.append(lines[i])
                        i += 1
                    blocks.append(f"{idx}\n{start} --> {end}\n" + "\n".join(text_lines))
                    idx += 1
                i += 1
            data = "\n\n".join(blocks).encode("utf-8")

        # send back as .srt
        buf = io.BytesIO(data)
        buf.name = "italian_subtitles.srt"
        query.message.reply_document(
            document=buf,
            filename="italian_subtitles.srt",
            caption="💬 Italian subtitles"
        )

    except Exception as e:
        logger.error("Subtitle processing error: %s", e)
        query.message.reply_text("⚠️ Could not download/process subtitles.")


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
