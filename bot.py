import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BOT_TOKEN, ADMIN_ID, TARGET_GROUP_ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

orders = []

# --- Состояния ---
class OrderState(StatesGroup):
    entering_order = State()
    confirming = State()

# --- Вспомогательные функции ---
def build_orders_text():
    if not orders:
        return "📭 Заказов пока нет."

    text = "📋 Список заказов:\n\n"
    for o in orders:
        status = "🟢 Свободен" if o["status"] == "free" else f"🔴 Взят (@{o.get('courier_username', '?')})"
        text += (
            f"#{o['number']} | {o['info']}\n"
            f"📌 {status}\n"
            f"{'─' * 25}\n"
        )
    return text

def build_orders_keyboard():
    """Список свободных заказов с кнопками взять"""
    builder = InlineKeyboardBuilder()
    available = [o for o in orders if o["status"] == "free"]
    for o in available:
        builder.button(
            text=f"📦 Взять #{o['number']}",
            callback_data=f"take_{o['number']}"
        )
    builder.adjust(1)
    return builder.as_markup() if available else None

def confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Опубликовать", callback_data="confirm_yes")
    builder.button(text="❌ Отменить", callback_data="confirm_no")
    builder.adjust(2)
    return builder.as_markup()

def orders_actions_keyboard():
    """Кнопки под списком заказов"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Опубликовать в группу", callback_data="publish_group")
    builder.adjust(1)
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
        "Введи всю информацию о заказе одним сообщением:\n\n"
        "Пример: Ленина 5, букет роз, позвонить за 30 минут"
    )
    await state.set_state(OrderState.entering_order)

@dp.message(OrderState.entering_order)
async def order_entered(message: Message, state: FSMContext):
    await state.update_data(info=message.text.strip())
    data = await state.get_data()
    await message.answer(
        f"📋 Проверь заказ:\n\n"
        f"📝 {data['info']}\n\n"
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
        "info": data["info"],
        "status": "free",
        "courier_username": None,
        "courier_id": None,
        "created_by": call.from_user.id,
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    orders.append(order)

    await call.message.edit_text(
        f"✅ Заказ #{order_number} создан!\n\n"
        f"📝 {data['info']}\n\n"
        f"Курьеры могут взять его через /orders"
    )
    await state.clear()

    # Показываем список с кнопками
    await call.message.answer(
        build_orders_text(),
        reply_markup=orders_actions_keyboard()
    )

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

    await message.answer(text, reply_markup=orders_actions_keyboard())

    if keyboard:
        await message.answer(
            "👇 Выбери заказ чтобы взять его:",
            reply_markup=keyboard
        )

# --- Публикация в группу ---
@dp.callback_query(F.data == "publish_group")
async def publish_to_group(call: CallbackQuery):
    if not orders:
        await call.answer("📭 Заказов пока нет.", show_alert=True)
        return

    available = [o for o in orders if o["status"] == "free"]
    if not available:
        await call.answer("⚠️ Нет свободных заказов.", show_alert=True)
        return

    text = build_orders_text()
    keyboard = build_orders_keyboard()

    await bot.send_message(TARGET_GROUP_ID, text, reply_markup=keyboard)
    await call.answer("✅ Заказы опубликованы в группу!", show_alert=True)

# --- Курьер берёт заказ ---
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

    order["status"] = "taken"
    order["courier_id"] = call.from_user.id
    order["courier_username"] = call.from_user.username or call.from_user.first_name


    
    )

    # Уведомление админу
    courier_name = f"@{order['courier_username']}" if call.from_user.username else order['courier_username']
    await bot.send_message(
        ADMIN_ID,
        f"🔔 Курьер взял заказ!\n\n"
        f"📦 Заказ #{order_number}\n"
        f"📝 {order['info']}\n"
        f"🚴 Курьер: {courier_name}"
    )

    # Обновляем сообщение в группе
    text = build_orders_text()
    keyboard = build_orders_keyboard()
    try:
        await call.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        pass

# --- Запуск ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())