
import os
from telegram import Update, KeyboardButton,   ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)   
from telegram import WebAppInfo
from dotenv import load_dotenv
load_dotenv()
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

async def start(update, context):

    keyboard = [
        [
            InlineKeyboardButton(
                "👑 OPEN FESHTA",
                web_app=WebAppInfo(
                    url="https://feshta.onrender.com"
                )
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👑 Welcome to FESHTA!\n\nEnter the Royal Arena and enjoy the games.",
        reply_markup=reply_markup
    )
async def menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    if text == "🎮 Play Games":
        # await update.message.reply_text(
        #     "🎮 Welcome to FESHTA Games!\n\n"
        #     "Choose your game. More games coming soon!"
        # )
        start();
    
    elif text == "💌 Invite Friends":
        await update.message.reply_text(
            "💌 Invite your friends to FESHTA!"
        )

    elif text == "🆘 Support":
        await update.message.reply_text(
            "🆘 Welcome to FESHTA Support!"
        )


def main():

    token = os.getenv("BOT_TOKEN")

    if not token:
        raise RuntimeError("BOT_TOKEN is missing!")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, menu_buttons)
    )

    print("FESHTA is running!")

    app.run_polling()


if __name__ == "__main__":
    main()
