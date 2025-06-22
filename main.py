import logging
import io
import requests
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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
    update.message.reply_text(
        "👋 Use /search <title> to look up a Donghua/Anime."
    )


def search(update: Update, context: CallbackContext):
    if not context.args:
        return update.message.reply_text("Usage: /search <series name>")

    query = " ".join(context.args)
    try:
        lst = search_series(query)
    except Exception:
        return update.message.reply_text("⚠️ API error.")

    if not lst:
        return update.message.reply_text(f"No series found for “{query}”.")

    series_map = {}
    buttons = []
    for i, s in enumerate(lst):
        slug = s.get("slug")
        title = s.get("title") or f"Series {i+1}"
        if not slug:
            continue
        series_map[str(i)] = slug
        buttons.append(
            [InlineKeyboardButton(title, callback_data=f"series#{i}")]
        )

    context.user_data["series_map"] = series_map
    update.message.reply_text(
        "Select a series:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


def series_callback(update: Update, context: CallbackContext):
    query = update.callback_query; query.answer()
    key = query.data.split("#")[1]
    slug = context.user_data.get("series_map", {}).get(key)
    if not slug:
        return query.edit_message_text("❌ Invalid series.")

    info = get_series_info(slug)
    title = info.get("title") or slug
    eps = info.get("episodes") or []
    if not isinstance(eps, list):
        eps = []

    if not eps:
        return query.edit_message_text(f"No episodes for **{title}**.", parse_mode="Markdown")

    ep_map, buttons = {}, []
    for i, ep in enumerate(eps):
        eslug = ep.get("ep_slug")
        num   = ep.get("episode_number") or (i+1)
        label = ep.get("title")       or f"Episode {num}"
        if not eslug:
            continue
        ep_map[str(i)] = eslug
        buttons.append([InlineKeyboardButton(label, callback_data=f"episode#{i}")])

    context.user_data["ep_map"] = ep_map
    query.edit_message_text(
        f"**{title}**\nSelect an episode:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )


def episode_callback(update: Update, context: CallbackContext):
    query = update.callback_query; query.answer()
    key = query.data.split("#")[1]
    ep_slug = context.user_data.get("ep_map", {}).get(key)
    if not ep_slug:
        return query.edit_message_text("❌ Invalid episode.")

    servers = get_episode_videos(ep_slug)
    sel = next(
        (s for s in servers
         if s["server_name"].lower().startswith("all sub player dailymotion")),
        None
    )
    if not sel:
        return query.edit_message_text("🚫 Dailymotion server not found.")

    # 1) send the video link
    query.message.reply_text(f"🎬 Video: {sel['video_url']}")

    # 2) fetch and convert the Italian subtitle
    sub_url = extract_italian_subtitle_url(sel["video_url"])
    if not sub_url:
        return query.message.reply_text("⚠️ Italian subtitle URL not found.")

    try:
        vtt = requests.get(sub_url).text.splitlines()
        srt_blocks, idx, i = [], 1, 0

        # Minimal VTT→SRT conversion
        while i < len(vtt):
            line = vtt[i].strip()
            if "-->" in line:
                # convert decimal point to comma
                start, end = line.split(" --> ")
                start = start.replace(".", ",")
                end   = end.replace(".", ",")
                texts = []
                i += 1
                while i < len(vtt) and vtt[i].strip():
                    texts.append(vtt[i])
                    i += 1
                block = f"{idx}\n{start} --> {end}\n" + "\n".join(texts)
                srt_blocks.append(block)
                idx += 1
            i += 1

        srt_data = "\n\n".join(srt_blocks).encode("utf-8")
        buf = io.BytesIO(srt_data)
        buf.name = "italian_subtitles.srt"

        query.message.reply_document(
            document=buf,
            filename="italian_subtitles.srt",
            caption="💬 Italian subtitles"
        )

    except Exception as e:
        logger.exception("Subtitle error")
        query.message.reply_text("⚠️ Failed to download/convert subtitles.")


def error_handler(update: object, context: CallbackContext):
    logger.error("Error", exc_info=context.error)
    if hasattr(update, "message") and update.message:
        update.message.reply_text("😵 Something broke.")
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
