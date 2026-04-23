import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BOT_TOKEN, ADMIN_ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

orders = []  # список всех заказов

# --- Состояния ---
class OrderState(StatesGroup):
    entering_address = State()
    entering_details = State()
    confirming = State()

# --- Вспомогательные функции ---
def build_orders_keyboard():
    """Список доступных заказов с кнопками взять"""
    builder = InlineKeyboardBuilder()
    available = [o for o in orders if o["status"] == "free"]
    for o in available:
        builder.button(
            text=f"📦 #{o['number']} | {o['address']}",
            callback_data=f"take_{o['number']}"
        )
    builder.adjust(1)
    return builder.as_markup() if available else None

def build_orders_text():
    """Текст со списком всех заказов"""
    if not orders:
        return "📭 Заказов пока нет."

    text = "📋 Список заказов:\n\n"
    for o in orders:
        status = "🟢 Свободен" if o["status"] == "free" else f"🔴 Взят (@{o.get('courier_username', '?')})"
        text += (
            f"#{o['number']} | {o['address']}\n"
            f"📝 {o['details']}\n"
            f"📌 {status}\n"
            f"{'─' * 25}\n"
        )
    return text

def confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Опубликовать", callback_data="confirm_yes")
    builder.button(text="❌ Отменить", callback_data="confirm_no")
    builder.adjust(2)
    return builder.as_markup()

# --- Хэндлеры ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет!\n\n"
        "Команды:\n"
        "/neworder — создать новый заказ\n"
        "/orders — посмотреть все заказы и взять один"
    )

@dp.message(F.text == "/neworder")
async def new_order(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📦 Создание нового заказа\n\n"
        "Шаг 1️⃣ — введи адрес доставки:"
    )
    await state.set_state(OrderState.entering_address)

@dp.message(OrderState.entering_address)
async def address_entered(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    await message.answer(
        "Шаг 2️⃣ — введи детали заказа:\n"
        "Пример: Букет роз, позвонить за 30 минут"
    )
    await state.set_state(OrderState.entering_details)

@dp.message(OrderState.entering_details)
async def details_entered(message: Message, state: FSMContext):
    await state.update_data(details=message.text.strip())
    data = await state.get_data()
    await message.answer(
        f"📋 Проверь заказ:\n\n"
        f"📍 Адрес: {data['address']}\n"
        f"📝 Детали: {data['details']}\n\n"
        f"Опубликовать?",
        reply_markup=confirm_keyboard()
    )
    await state.set_state(OrderState.confirming)

@dp.callback_query(OrderState.confirming, F.data == "confirm_yes")
async def order_published(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    order_number = len(orders) + 1
    order = {
        "number": order_number,
        "address": data["address"],
        "details": data["details"],
        "status": "free",
        "courier_username": None,
        "courier_id": None,
        "created_by": call.from_user.id,
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    orders.append(order)

    await call.message.edit_text(
        f"✅ Заказ #{order_number} опубликован!\n\n"
        f"📍 {data['address']}\n"
        f"📝 {data['details']}\n\n"
        f"Курьеры могут взять его через /orders"
    )
    await state.clear()

@dp.callback_query(OrderState.confirming, F.data == "confirm_no")
async def order_cancelled(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "❌ Создание заказа отменено. Попробуй снова — /neworder"
    )

@dp.message(F.text == "/orders")
async def show_orders(message: Message):
    text = build_orders_text()
    keyboard = build_orders_keyboard()

    if keyboard:
        await message.answer(text)
        await message.answer(
            "👇 Выбери заказ чтобы взять его:",
            reply_markup=keyboard
        )
    else:
        await message.answer(text + "\n\nСвободных заказов нет.")

@dp.callback_query(F.data.startswith("take_"))
async def take_order(call: CallbackQuery):
    order_number = int(call.data.split("_")[1])
    order = next((o for o in orders if o["number"] == order_number), None)

    if not order:
        await call.answer("⚠️ Заказ не найден.", show_alert=True)
        return

    if order["status"] != "free":
        await call.answer("⚠️ Этот заказ уже взят!", show_alert=True)
        return

    # Курьер берёт заказ
    order["status"] = "taken"
    order["courier_id"] = call.from_user.id
    order["courier_username"] = call.from_user.username or call.from_user.first_name

    await call.answer(f"✅ Ты взял заказ #{order_number}!", show_alert=True)

    await call.message.answer(
        f"🚴 Ты взял заказ #{order_number}!\n\n"
        f"📍 Адрес: {order['address']}\n"
        f"📝 Детали: {order['details']}\n\n"
        f"Удачной доставки! 💪"
    )

    # Уведомление админу
    courier_name = f"@{order['courier_username']}" if call.from_user.username else order['courier_username']
    await bot.send_message(
        ADMIN_ID,
        f"🔔 Курьер взял заказ!\n\n"
        f"📦 Заказ #{order_number}\n"
        f"📍 {order['address']}\n"
        f"📝 {order['details']}\n"
        f"🚴 Курьер: {courier_name}"
    )

    # Обновляем список
    text = build_orders_text()
    keyboard = build_orders_keyboard()
    if keyboard:
        await call.message.edit_text(text)
        await call.message.answer(
            "👇 Оставшиеся свободные заказы:",
            reply_markup=keyboard
        )
    else:
        await call.message.edit_text(text)

# --- Запуск ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())