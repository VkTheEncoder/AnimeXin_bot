import logging
import io
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
    download_subtitles_with_ytdlp,
    translate_srt,
)

# — Logging setup —
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

PAGE_SIZE = 10

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

    context.user_data["series_list"] = series_list
    context.user_data["series_page"] = 0
    _show_series_page(update, context, page=0)

def _show_series_page(update_or_query, context: CallbackContext, page: int):
    series_list = context.user_data["series_list"]
    total = len(series_list)
    start_i = page * PAGE_SIZE
    end_i = min(start_i + PAGE_SIZE, total)

    buttons = [
        [InlineKeyboardButton(
            series_list[i]["title"] or f"Series {i+1}",
            callback_data=f"series_select#{i}"
        )]
        for i in range(start_i, end_i)
    ]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("« Prev", callback_data=f"series_page#{page-1}"))
    if end_i < total:
        nav.append(InlineKeyboardButton("Next »", callback_data=f"series_page#{page+1}"))
    if nav:
        buttons.append(nav)

    markup = InlineKeyboardMarkup(buttons)
    text = "Select a series:"
    if hasattr(update_or_query, "message"):
        update_or_query.message.reply_text(text, reply_markup=markup)
    else:
        update_or_query.edit_message_text(text, reply_markup=markup)

    context.user_data["series_page"] = page

def series_page_callback(update: Update, context: CallbackContext):
    q = update.callback_query; q.answer()
    page = int(q.data.split("#",1)[1])
    _show_series_page(q, context, page)

def series_select_callback(update: Update, context: CallbackContext):
    q = update.callback_query; q.answer()
    idx = int(q.data.split("#",1)[1])
    series_list = context.user_data.get("series_list", [])
    if idx < 0 or idx >= len(series_list):
        return q.edit_message_text("❌ Invalid selection.")

    slug = series_list[idx]["slug"]
    context.user_data["current_series_idx"] = idx
    context.user_data["episode_page"] = 0

    try:
        info = get_series_info(slug)
    except Exception as e:
        logger.error("Series info error: %s", e)
        return q.edit_message_text("⚠️ Could not fetch series info.")

    title = info.get("title") or slug
    context.user_data["episode_list"] = info.get("episodes") or []
    _show_episode_page(q, context, title, page=0)

def _show_episode_page(query, context: CallbackContext, title: str, page: int):
    episodes = context.user_data["episode_list"]
    total = len(episodes)
    start_i = page * PAGE_SIZE
    end_i = min(start_i + PAGE_SIZE, total)

    buttons = [
        [InlineKeyboardButton(
            episodes[i]["title"] or f"Episode {episodes[i].get('episode_number', i+1)}",
            callback_data=f"episode_select#{i}"
        )]
        for i in range(start_i, end_i)
    ]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("« Prev", callback_data=f"episode_page#{page-1}"))
    if end_i < total:
        nav.append(InlineKeyboardButton("Next »", callback_data=f"episode_page#{page+1}"))
    nav.append(InlineKeyboardButton("« Back", callback_data="back_to_series"))
    if nav:
        buttons.append(nav)

    markup = InlineKeyboardMarkup(buttons)
    text = f"**{title}**\nSelect an episode:"
    query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    context.user_data["episode_page"] = page

def episode_page_callback(update: Update, context: CallbackContext):
    q = update.callback_query; q.answer()
    page = int(q.data.split("#",1)[1])
    idx = context.user_data.get("current_series_idx", 0)
    title = context.user_data["series_list"][idx].get("title")
    _show_episode_page(q, context, title, page)

def back_to_series_callback(update: Update, context: CallbackContext):
    q = update.callback_query; q.answer()
    page = context.user_data.get("series_page", 0)
    _show_series_page(q, context, page)

def episode_select_callback(update: Update, context: CallbackContext):
    q = update.callback_query; q.answer()
    idx = int(q.data.split("#",1)[1])
    episodes = context.user_data.get("episode_list", [])
    if idx < 0 or idx >= len(episodes):
        return q.edit_message_text("❌ Invalid selection.")

    ep_slug = episodes[idx]["ep_slug"]
    try:
        servers = get_episode_videos(ep_slug)
    except Exception as e:
        logger.error("Episode videos error: %s", e)
        return q.edit_message_text("⚠️ Could not fetch episode video links.")

    selected = next(
        (s for s in servers if s["server_name"].lower().startswith("all sub player dailymotion")),
        None
    )
    if not selected:
        return q.edit_message_text("🚫 Dailymotion server not available.")

    video_url = selected["video_url"]
    q.message.reply_text(f"🎬 Video (Dailymotion)\n{video_url}")

    # download Italian subtitles
    italian_data = download_subtitles_with_ytdlp(video_url, lang="it")
    if not italian_data:
        return q.message.reply_text("⚠️ Italian subtitles not found.")

    # send original Italian .srt
    buf_it = io.BytesIO(italian_data)
    buf_it.name = "subtitles_it.srt"
    q.message.reply_document(document=buf_it, filename="subtitles_it.srt", caption="💬 Italian subtitles")

    # translate to English and send
    try:
        english_data = translate_srt(italian_data, src="it", dest="en")
        buf_en = io.BytesIO(english_data)
        buf_en.name = "subtitles_en.srt"
        q.message.reply_document(document=buf_en, filename="subtitles_en.srt", caption="💬 English subtitles")
    except Exception as e:
        logger.error("Subtitle translation error: %s", e)
        q.message.reply_text("⚠️ Failed to translate subtitles.")

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

    dp.add_handler(CallbackQueryHandler(series_page_callback, pattern=r"^series_page#"))
    dp.add_handler(CallbackQueryHandler(series_select_callback, pattern=r"^series_select#"))

    dp.add_handler(CallbackQueryHandler(episode_page_callback, pattern=r"^episode_page#"))
    dp.add_handler(CallbackQueryHandler(back_to_series_callback, pattern=r"^back_to_series$"))
    dp.add_handler(CallbackQueryHandler(episode_select_callback, pattern=r"^episode_select#"))

    dp.add_error_handler(error_handler)

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
