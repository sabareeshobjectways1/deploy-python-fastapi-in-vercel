import logging
from telegram import Update, ChatMember
from telegram.ext import (filters, ApplicationBuilder, ContextTypes, CommandHandler, ConversationHandler,
                          MessageHandler, ChatMemberHandler)
from UserStatus import UserStatus
from config import BOT_TOKEN, ADMIN_ID
import db_connection

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING  # Set the logging level to: (DEBUG, INFO, WARNING, ERROR, CRITICAL)
)

"""
####### List of commands #######
---> start - 🤖 starts the bot
---> chat - 💬 start searching for a partner
---> exit - 🔚 exit from the chat
---> newchat - ⏭ exit from the chat and open a new one
---> stats - 📊 show bot statistics (only for admin)
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Welcome to this ChatBot! 🤖\nType /chat to start searching for a partner")
    user_id = update.effective_user.id
    db_connection.insert_user(user_id)
    return USER_ACTION

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if db_connection.get_user_status(user_id=user_id) == UserStatus.COUPLED:
        other_user_id = db_connection.get_partner_id(user_id)
        if other_user_id is None:
            return await handle_not_in_chat(update, context)
        else:
            return await in_chat(update, other_user_id)
    else:
        return await handle_not_in_chat(update, context)

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user_id = update.effective_user.id
    current_user_status = db_connection.get_user_status(user_id=current_user_id)

    if current_user_status == UserStatus.PARTNER_LEFT:
        db_connection.set_user_status(user_id=current_user_id, new_status=UserStatus.IDLE)
        return await start_search(update, context)
    elif current_user_status == UserStatus.IN_SEARCH:
        return await handle_already_in_search(update, context)
    elif current_user_status == UserStatus.COUPLED:
        other_user = db_connection.get_partner_id(current_user_id)
        if other_user is not None:
            await context.bot.send_message(chat_id=current_user_id,
                                           text="🤖 You are already in a chat, type /exit to exit from the chat.")
            return None
        else:
            return await start_search(update, context)
    elif current_user_status == UserStatus.IDLE:
        return await start_search(update, context)

async def handle_not_in_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user_id = update.effective_user.id
    current_user_status = db_connection.get_user_status(user_id=current_user_id)

    if current_user_status in [UserStatus.IDLE, UserStatus.PARTNER_LEFT]:
        await context.bot.send_message(chat_id=current_user_id,
                                       text="🤖 You are not in a chat, type /chat to start searching for a partner.")
        return
    elif current_user_status == UserStatus.IN_SEARCH:
        await context.bot.send_message(chat_id=current_user_id,
                                       text="🤖 Message not delivered, you are still in search!")
        return

async def handle_already_in_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(chat_id=update.effective_chat.id, text="🤖 You are already in search!")
    return

async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user_id = update.effective_chat.id
    db_connection.set_user_status(user_id=current_user_id, new_status=UserStatus.IN_SEARCH)
    await context.bot.send_message(chat_id=current_user_id, text="🤖 Searching for a partner...")
    other_user_id = db_connection.couple(current_user_id=current_user_id)
    if other_user_id is not None:
        await context.bot.send_message(chat_id=current_user_id, text="🤖 You have been paired with an user")
        await context.bot.send_message(chat_id=other_user_id, text="🤖 You have been paired with an user")
    return

async def handle_exit_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await exit_chat(update, context)
    return

async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        total_users_number, paired_users_number = db_connection.retrieve_users_number()
        await context.bot.send_message(chat_id=user_id, text="Welcome to the admin panel")
        await context.bot.send_message(chat_id=user_id,
                                       text="Number of paired users: " + str(paired_users_number))
        await context.bot.send_message(chat_id=user_id,
                                       text="Number of active users: " + str(total_users_number))
    else:
        logging.warning("User " + str(user_id) + " tried to access the admin panel")
    return

async def exit_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user = update.effective_user.id
    if db_connection.get_user_status(user_id=current_user) != UserStatus.COUPLED:
        await context.bot.send_message(chat_id=current_user, text="🤖 You are not in a chat!")
        return
    other_user = db_connection.get_partner_id(current_user)
    if other_user is None:
        return
    db_connection.uncouple(user_id=current_user)
    await context.bot.send_message(chat_id=current_user, text="🤖 Ending chat...")
    await context.bot.send_message(chat_id=other_user,
                                   text="🤖 Your partner has left the chat, type /chat to start searching for a new "
                                        "partner.")
    await update.message.reply_text("🤖 You have left the chat.")
    return

async def exit_then_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_user = update.effective_user.id
    if db_connection.get_user_status(user_id=current_user) == UserStatus.IN_SEARCH:
        return await handle_already_in_search(update, context)
    await exit_chat(update, context)
    return await start_search(update, context)

async def in_chat(update: Update, other_user_id) -> None:
    if update.message.reply_to_message is not None:
        if update.message.reply_to_message.from_user.id == update.effective_user.id:
            await update.effective_chat.copy_message(chat_id=other_user_id, message_id=update.message.message_id,
                                                     protect_content=True,
                                                     reply_to_message_id=update.message.reply_to_message.message_id + 1)
        elif update.message.reply_to_message.has_protected_content is None:
            await update.effective_chat.copy_message(chat_id=other_user_id, message_id=update.message.message_id,
                                                     protect_content=True)
        else:
            await update.effective_chat.copy_message(chat_id=other_user_id, message_id=update.message.message_id,
                                                     protect_content=True,
                                                     reply_to_message_id=update.message.reply_to_message.message_id - 1)
    else:
        await update.effective_chat.copy_message(chat_id=other_user_id, message_id=update.message.message_id,
                                                 protect_content=True)
    return

def is_bot_blocked_by_user(update: Update) -> bool:
    new_member_status = update.my_chat_member.new_chat_member.status
    old_member_status = update.my_chat_member.old_chat_member.status
    return new_member_status == ChatMember.BANNED and old_member_status == ChatMember.MEMBER

async def blocked_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_bot_blocked_by_user(update):
        user_id = update.effective_user.id
        user_status = db_connection.get_user_status(user_id=user_id)
        if user_status == UserStatus.COUPLED:
            other_user = db_connection.get_partner_id(user_id)
            db_connection.uncouple(user_id=user_id)
            await context.bot.send_message(chat_id=other_user, text="🤖 Your partner has left the chat, type /chat to "
                                                                    "start searching for a new partner.")
        db_connection.remove_user(user_id=user_id)
        return ConversationHandler.END
    else:
        return USER_ACTION

USER_ACTION = 0

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    db_connection.create_db()
    db_connection.reset_users_status()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            USER_ACTION: [
                ChatMemberHandler(blocked_bot_handler),
                MessageHandler(
                    (filters.TEXT | filters.ATTACHMENT) & ~ filters.COMMAND & ~filters.Regex("exit") & ~filters.Regex(
                        "chat")
                    & ~filters.Regex("newchat") & ~filters.Regex("stats"),
                    handle_message),
                CommandHandler("exit", handle_exit_chat),
                CommandHandler("chat", handle_chat),
                CommandHandler("newchat", exit_then_chat),
                CommandHandler("stats", handle_stats)]
        },
        fallbacks=[MessageHandler(filters.TEXT, handle_not_in_chat)]
    )
    application.add_handler(conv_handler)
    application.run_polling()
  
