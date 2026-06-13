import asyncio
import json
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RECIPES_PATH = Path(__file__).parent / "recipes.json"

with RECIPES_PATH.open(encoding="utf-8") as file:
    RECIPES: dict[str, dict[str, int]] = json.load(file)

DISH_LIST = list(RECIPES.keys())

# Ингредиенты, которые считаются в штуках (остальные — в граммах)
PIECE_UNITS = {"Яйцо", "Лук"}

# user_id -> множество выбранных блюд
user_selections: dict[int, set[str]] = {}

GENERATE_CALLBACK = "generate"


def format_amount(ingredient: str, amount: int) -> str:
    if ingredient in PIECE_UNITS:
        return f"{amount} шт."
    return f"{amount} г"


def build_keyboard(user_id: int) -> InlineKeyboardMarkup:
    selected = user_selections.get(user_id, set())
    rows: list[list[InlineKeyboardButton]] = []

    for index, dish in enumerate(DISH_LIST):
        mark = "✅ " if dish in selected else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{dish}",
                    callback_data=f"dish:{index}",
                )
            ]
        )

    rows.append(
        [InlineKeyboardButton(text="Сгенерировать список покупок", callback_data=GENERATE_CALLBACK)]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_shopping_list(selected: set[str]) -> str:
    totals: dict[str, int] = {}
    for dish in selected:
        for ingredient, amount in RECIPES[dish].items():
            totals[ingredient] = totals.get(ingredient, 0) + amount

    dishes_block = "\n".join(f"  • {dish}" for dish in sorted(selected))
    ingredients_block = "\n".join(
        f"  • {name} — {format_amount(name, amount)}"
        for name, amount in sorted(totals.items())
    )

    return (
        "🛒 <b>Список покупок на неделю</b>\n\n"
        f"<b>Выбранные блюда:</b>\n{dishes_block}\n\n"
        f"<b>Ингредиенты:</b>\n{ingredients_block}"
    )


async def update_keyboard(callback: CallbackQuery, user_id: int) -> None:
    try:
        await callback.message.edit_reply_markup(reply_markup=build_keyboard(user_id))
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id
    user_selections.setdefault(user_id, set())

    await message.answer(
        "👋 Привет! Я помогу спланировать покупки на неделю.\n\n"
        "Нажимайте на блюда, чтобы выбрать их. Выбранные отмечены галочкой ✅.\n"
        "Когда закончите — нажмите «Сгенерировать список покупок».",
        reply_markup=build_keyboard(user_id),
    )


async def on_dish_toggle(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    index = int(callback.data.removeprefix("dish:"))
    dish = DISH_LIST[index]

    selected = user_selections.setdefault(user_id, set())
    if dish in selected:
        selected.remove(dish)
        await callback.answer(f"Убрано: {dish}")
    else:
        selected.add(dish)
        await callback.answer(f"Добавлено: {dish}")

    await update_keyboard(callback, user_id)


async def on_generate(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    selected = user_selections.get(user_id, set())

    if not selected:
        await callback.answer("Сначала выберите хотя бы одно блюдо!", show_alert=True)
        return

    await callback.answer()
    await callback.message.answer(
        build_shopping_list(selected),
        parse_mode=ParseMode.HTML,
    )

    user_selections[user_id] = set()
    await update_keyboard(callback, user_id)


async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Переменная BOT_TOKEN не задана в .env")

    bot = Bot(token=token)
    dp = Dispatcher()

    dp.message.register(cmd_start, CommandStart())
    dp.callback_query.register(on_dish_toggle, F.data.startswith("dish:"))
    dp.callback_query.register(on_generate, F.data == GENERATE_CALLBACK)

    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
