# main.py
import logging
import io
import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext, DispatcherHandlerStop
)
import config
from utils import (
    search_series, get_series_info, get_episode_videos,
    download_subtitles_with_ytdlp
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
PAGE_SIZE = 10

# Helper to show paginated list
def paginate(items, page):
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    return items[start:end], start, end

# —— Bot Handlers ——
def start(update: Update, context: CallbackContext):
    update.message.reply_text("👋 Welcome! Use /search <title>.")


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
        return update.message.reply_text(f"No results for “{query}”.")
    context.user_data['series_list'] = lst
    context.user_data['series_page'] = 0
    show_series_page(update, context)


def show_series_page(update_or_cb, context: CallbackContext, edit=False):
    data = context.user_data['series_list']
    page = context.user_data.get('series_page', 0)
    page_items, start, end = paginate(data, page)
    buttons = []
    for idx, item in enumerate(page_items, start=start):
        title = item.get('title') or f"Series {idx+1}"
        buttons.append([InlineKeyboardButton(title, callback_data=f"series_select#{idx}")])
    # nav
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton('« Prev', callback_data=f"series_page#{page-1}"))
    if end < len(data):
        nav.append(InlineKeyboardButton('Next »', callback_data=f"series_page#{page+1}"))
    if nav:
        buttons.append(nav)
    markup = InlineKeyboardMarkup(buttons)
    if edit:
        update_or_cb.edit_message_text('Select a series:', reply_markup=markup)
    else:
        update_or_cb.message.reply_text('Select a series:', reply_markup=markup)


def series_page_callback(update: Update, context: CallbackContext):
    query = update.callback_query; query.answer()
    page = int(query.data.split('#')[1])
    context.user_data['series_page'] = page
    show_series_page(query, context, edit=True)


def series_select_callback(update: Update, context: CallbackContext):
    query = update.callback_query; query.answer()
    idx = int(query.data.split('#')[1])
    slug = context.user_data['series_list'][idx].get('slug')
    context.user_data['current_series_slug'] = slug
    # fetch episodes
    info = get_series_info(slug)
    eps = info.get('episodes') or []
    context.user_data['episode_list'] = eps
    context.user_data['episode_page'] = 0
    show_episode_page(query, context, edit=True)


def show_episode_page(update_or_cb, context: CallbackContext, edit=False):
    eps = context.user_data['episode_list']
    page = context.user_data.get('episode_page', 0)
    page_items, start, end = paginate(eps, page)
    buttons = []
    for idx, ep in enumerate(page_items, start=start):
        num = ep.get('episode_number') or (idx+1)
        label = ep.get('title') or f"Episode {num}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"episode_select#{idx}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton('« Prev', callback_data=f"episode_page#{page-1}"))
    if end < len(eps):
        nav.append(InlineKeyboardButton('Next »', callback_data=f"episode_page#{page+1}"))
    if nav:
        buttons.append(nav)
    markup = InlineKeyboardMarkup(buttons)
    prefix = f"**{context.user_data.get('current_series_slug')}**\nSelect an episode:"
    if edit:
        update_or_cb.edit_message_text(prefix, reply_markup=markup, parse_mode="Markdown")
    else:
        update_or_cb.message.reply_text(prefix, reply_markup=markup, parse_mode="Markdown")


def episode_page_callback(update: Update, context: CallbackContext):
    query = update.callback_query; query.answer()
    page = int(query.data.split('#')[1])
    context.user_data['episode_page'] = page
    show_episode_page(query, context, edit=True)


def episode_select_callback(update: Update, context: CallbackContext):
    query = update.callback_query; query.answer()
    idx = int(query.data.split('#')[1])
    ep = context.user_data['episode_list'][idx]
    ep_slug = ep.get('ep_slug')
    # fetch servers
    servers = get_episode_videos(ep_slug)
    sel = next((s for s in servers if s['server_name'].lower().startswith('all sub player dailymotion')), None)
    if not sel:
        return query.edit_message_text("🚫 Dailymotion server not available.")
    video_url = sel.get('video_url')
    query.message.reply_text(f"🎬 Video (Dailymotion)\n{video_url}")
    data = download_subtitles_with_ytdlp(video_url, lang='it')
    if not data:
        return query.message.reply_text("⚠️ Italian subtitles not found via yt-dlp.")
    buf = io.BytesIO(data)
    buf.name = 'italian_subtitles.srt'
    query.message.reply_document(document=buf, filename='italian_subtitles.srt', caption='💬 Italian subtitles')


def error_handler(update: object, context: CallbackContext):
    logger.error("Error", exc_info=context.error)
    if update and getattr(update, 'message', None):
        update.message.reply_text("😵 Something went wrong.")
    raise DispatcherHandlerStop()


def main():
    updater = Updater(config.TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('search', search))
    dp.add_handler(CallbackQueryHandler(series_page_callback, pattern=r"^series_page#"))
    dp.add_handler(CallbackQueryHandler(series_select_callback, pattern=r"^series_select#"))
    dp.add_handler(CallbackQueryHandler(episode_page_callback, pattern=r"^episode_page#"))
    dp.add_handler(CallbackQueryHandler(episode_select_callback, pattern=r"^episode_select#"))
    dp.add_error_handler(error_handler)
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
