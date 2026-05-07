import asyncio
import logging
import os
import sys

import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BOT_TOKEN

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
API_BASE = "http://localhost:8000"
user_states: dict = {}


class ProfileCreation(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_gender = State()
    waiting_for_city = State()
    waiting_for_bio = State()
    waiting_for_photo = State()


class ProfileEdit(StatesGroup):
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_bio = State()


async def api_request(method: str, endpoint: str, json_data: dict = None):
    async with aiohttp.ClientSession() as session:
        try:
            timeout = aiohttp.ClientTimeout(total=7)
            if method == "GET":
                async with session.get(f"{API_BASE}{endpoint}", timeout=timeout) as resp:
                    return await resp.json()
            if method == "PUT":
                async with session.put(f"{API_BASE}{endpoint}", json=json_data, timeout=timeout) as resp:
                    return await resp.json()
            async with session.post(f"{API_BASE}{endpoint}", json=json_data, timeout=timeout) as resp:
                return await resp.json()
        except asyncio.TimeoutError:
            return {"error": "Сервер долго отвечает, попробуйте через минуту."}
        except Exception as exc:
            logger.error("API error on %s: %s", endpoint, exc)
            return {"error": str(exc)}


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💘 Смотреть анкеты"), KeyboardButton(text="📝 Моя анкета")],
            [KeyboardButton(text="📷 Добавить фото")],
            [KeyboardButton(text="🔄 Обновить выдачу")],
        ],
        resize_keyboard=True,
    )


def gender_keyboard(prefix: str = "gender") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👨 Мужчина", callback_data=f"{prefix}_male")],
            [InlineKeyboardButton(text="👩 Женщина", callback_data=f"{prefix}_female")],
            [InlineKeyboardButton(text="🌍 Не важно", callback_data=f"{prefix}_any")],
        ]
    )


def like_keyboard(profile_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💚 Лайк", callback_data=f"like:{profile_id}"),
                InlineKeyboardButton(text="👎 Скип", callback_data=f"skip:{profile_id}"),
            ],
            [InlineKeyboardButton(text="⏸ Пауза", callback_data="pause_search")],
        ]
    )


def profile_keyboard(profile: dict, photo_index: int = 0) -> InlineKeyboardMarkup:
    profile_id = profile["id"]
    photos = profile.get("photos", []) or []
    photo_items = [item["file_id"] if isinstance(item, dict) else item for item in photos]
    controls = [InlineKeyboardButton(text="📷 1/1", callback_data="photo_noop")]
    if len(photo_items) > 1:
        controls = [
            InlineKeyboardButton(text="⬅️", callback_data=f"photo_prev:{profile_id}:{photo_index}"),
            InlineKeyboardButton(text=f"{photo_index + 1}/{len(photo_items)}", callback_data="photo_noop"),
            InlineKeyboardButton(text="➡️", callback_data=f"photo_next:{profile_id}:{photo_index}"),
        ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💚 Лайк", callback_data=f"like:{profile_id}"),
                InlineKeyboardButton(text="👎 Скип", callback_data=f"skip:{profile_id}"),
            ],
            controls,
            [InlineKeyboardButton(text="⏸ Пауза", callback_data="pause_search")],
        ]
    )


def profile_text(profile: dict) -> str:
    return (
        f"👤 {profile.get('name', 'Пользователь')}\n"
        f"🎂 {profile.get('age', '?')} | {profile.get('gender', '?')}\n"
        f"📍 {profile.get('city', 'Не указан')}\n"
        f"📷 Фото: {profile.get('photos_count', 0)}\n"
        f"📝 {profile.get('bio', 'Без описания')[:150]}\n"
        f"⭐ Рейтинг: {profile.get('rating_score', 0)}"
    )


async def send_profile_card(message: types.Message, profile: dict, photo_index: int = 0):
    photos = profile.get("photos", []) or []
    photo_items = [item["file_id"] if isinstance(item, dict) else item for item in photos]
    if photo_items:
        idx = max(0, min(photo_index, len(photo_items) - 1))
        await message.answer_photo(
            photo=photo_items[idx],
            caption=profile_text(profile),
            reply_markup=profile_keyboard(profile, idx),
        )
    else:
        await message.answer(profile_text(profile), reply_markup=profile_keyboard(profile, 0))


def profile_manage_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Имя", callback_data="edit_name"),
                InlineKeyboardButton(text="🎂 Возраст", callback_data="edit_age"),
            ],
            [
                InlineKeyboardButton(text="📝 Описание", callback_data="edit_bio"),
                InlineKeyboardButton(text="📷 Фото", callback_data="edit_photo"),
            ],
            [InlineKeyboardButton(text="🆕 Заполнить заново", callback_data="recreate_profile")],
        ]
    )


def photo_manage_keyboard(profile: dict) -> InlineKeyboardMarkup:
    photos = profile.get("photos", []) or []
    rows = []
    for idx, photo in enumerate(photos[:10], start=1):
        photo_id = photo["id"] if isinstance(photo, dict) else idx
        rows.append([InlineKeyboardButton(text=f"🗑️ Удалить фото {idx}", callback_data=f"delete_photo:{photo_id}")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def replace_profile_message(source_message: types.Message, profile: dict):
    photos = profile.get("photos", []) or []
    photo_items = [item["file_id"] if isinstance(item, dict) else item for item in photos]
    try:
        await source_message.delete()
    except Exception:
        pass
    if photo_items:
        await source_message.answer_photo(photo=photo_items[0], caption=profile_text(profile), reply_markup=profile_keyboard(profile, 0))
    else:
        await source_message.answer(profile_text(profile), reply_markup=profile_keyboard(profile, 0))


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    telegram_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name or f"user_{telegram_id}"
    result = await api_request("POST", "/user/register", {"telegram_id": telegram_id, "username": username})
    if "error" in result:
        await message.answer("⚠️ Не удалось подключиться к backend. Проверьте, что API запущен.")
        return
    user_states[telegram_id] = {"user_id": result["user_id"]}
    await message.answer(
        "Привет! Это мини-дайтинг в стиле Дайвинчика.\n"
        "Сначала заполни анкету, потом листай выдачу свайп-кнопками.",
        reply_markup=main_menu(),
    )


@dp.message(Command("create_profile"))
async def start_profile_creation(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Как тебя зовут?", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ProfileCreation.waiting_for_name)


@dp.message(ProfileCreation.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Имя короткое, попробуй еще раз.")
        return
    await state.update_data(name=name)
    await message.answer("Сколько тебе лет? (18-100)")
    await state.set_state(ProfileCreation.waiting_for_age)


@dp.message(ProfileCreation.waiting_for_age)
async def process_age(message: types.Message, state: FSMContext):
    try:
        age = int(message.text)
    except (TypeError, ValueError):
        await message.answer("Нужна цифра, например 24.")
        return
    if not 18 <= age <= 100:
        await message.answer("Возраст должен быть в диапазоне 18-100.")
        return
    await state.update_data(age=age)
    await message.answer("Выбери свой пол:", reply_markup=gender_keyboard(prefix="mygender"))
    await state.set_state(ProfileCreation.waiting_for_gender)


@dp.callback_query(ProfileCreation.waiting_for_gender, F.data.startswith("mygender_"))
async def process_gender(cb: types.CallbackQuery, state: FSMContext):
    mapping = {"mygender_male": "М", "mygender_female": "Ж", "mygender_any": "Не указан"}
    await state.update_data(gender=mapping.get(cb.data, "Не указан"))
    await cb.message.answer("Из какого ты города?")
    await state.set_state(ProfileCreation.waiting_for_city)
    await cb.answer()


@dp.message(ProfileCreation.waiting_for_city)
async def process_city(message: types.Message, state: FSMContext):
    city = (message.text or "").strip()
    if len(city) < 2:
        await message.answer("Укажи город корректно.")
        return
    await state.update_data(city=city)
    await message.answer("Коротко о себе (от 10 символов):")
    await state.set_state(ProfileCreation.waiting_for_bio)


@dp.message(ProfileCreation.waiting_for_bio)
async def process_bio(message: types.Message, state: FSMContext):
    bio = (message.text or "").strip()
    if len(bio) < 10:
        await message.answer("Слишком коротко, добавь деталей.")
        return
    await state.update_data(bio=bio)
    payload = await state.get_data()
    telegram_id = message.from_user.id
    if telegram_id not in user_states:
        await message.answer("Сессия сброшена. Нажми /start.")
        await state.clear()
        return

    result = await api_request(
        "POST",
        "/profile/create",
        {
            "user_id": user_states[telegram_id]["user_id"],
            "name": payload["name"],
            "age": payload["age"],
            "gender": payload["gender"],
            "city": payload["city"],
            "bio": payload["bio"],
        },
    )

    if "error" in result:
        await message.answer(f"Не удалось создать анкету: {result['error']}", reply_markup=main_menu())
        await state.clear()
    else:
        await message.answer(
            "Анкета создана ✅\nТеперь отправь фото для анкеты (можно несколько). Когда закончишь, нажми «Готово».",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="✅ Готово", callback_data="finish_photo_upload")]]
            ),
        )
        await state.set_state(ProfileCreation.waiting_for_photo)


@dp.callback_query(ProfileCreation.waiting_for_photo, F.data == "finish_photo_upload")
async def finish_photo_upload(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer(
        "Профиль заполнен. Можешь смотреть анкеты или открыть «Моя анкета».",
        reply_markup=main_menu(),
    )
    await cb.answer()


@dp.message(F.text == "📝 Моя анкета")
@dp.message(Command("profile"))
async def show_my_profile(message: types.Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    if telegram_id not in user_states:
        await message.answer("Сначала нажми /start.")
        return

    user_id = user_states[telegram_id]["user_id"]
    profile = await api_request("GET", f"/profile/{user_id}")
    if "detail" in profile:
        await message.answer(
            "Анкета еще не создана. Давай заполним ее сейчас.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.set_state(ProfileCreation.waiting_for_name)
        await message.answer("Как тебя зовут?")
        return

    text = (
        "Твоя анкета:\n"
        f"👤 {profile.get('name', '-')}\n"
        f"🎂 {profile.get('age', '-')}\n"
        f"📝 {profile.get('bio', '-')}\n"
        f"📷 Фото: {len(profile.get('photos', []))}"
    )
    await message.answer(text, reply_markup=profile_manage_keyboard())


@dp.callback_query(F.data == "recreate_profile")
async def recreate_profile(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("Заполняем заново. Как тебя зовут?", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ProfileCreation.waiting_for_name)
    await cb.answer()


@dp.callback_query(F.data == "edit_name")
async def edit_name_start(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(ProfileEdit.waiting_for_name)
    await cb.message.answer("Введи новое имя:")
    await cb.answer()


@dp.callback_query(F.data == "edit_age")
async def edit_age_start(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(ProfileEdit.waiting_for_age)
    await cb.message.answer("Введи новый возраст (18-100):")
    await cb.answer()


@dp.callback_query(F.data == "edit_bio")
async def edit_bio_start(cb: types.CallbackQuery, state: FSMContext):
    await state.set_state(ProfileEdit.waiting_for_bio)
    await cb.message.answer("Введи новое описание (от 10 символов):")
    await cb.answer()


@dp.callback_query(F.data == "edit_photo")
async def edit_photo_start(cb: types.CallbackQuery):
    telegram_id = cb.from_user.id
    user_id = user_states.get(telegram_id, {}).get("user_id")
    profile = await api_request("GET", f"/profile/{user_id}")
    if "detail" in profile:
        await cb.message.answer("Сначала создай анкету.")
    else:
        await cb.message.answer(
            f"Фото в анкете: {len(profile.get('photos', []))}\n"
            "Отправь новое фото сообщением или удали существующее:",
            reply_markup=photo_manage_keyboard(profile),
        )
    await cb.answer()


@dp.callback_query(F.data == "back_to_profile")
async def back_to_profile(cb: types.CallbackQuery):
    telegram_id = cb.from_user.id
    user_id = user_states.get(telegram_id, {}).get("user_id")
    profile = await api_request("GET", f"/profile/{user_id}")
    if "detail" in profile:
        await cb.message.answer("Анкета не найдена.")
    else:
        text = (
            "Твоя анкета:\n"
            f"👤 {profile.get('name', '-')}\n"
            f"🎂 {profile.get('age', '-')}\n"
            f"📝 {profile.get('bio', '-')}\n"
            f"📷 Фото: {len(profile.get('photos', []))}"
        )
        await cb.message.answer(text, reply_markup=profile_manage_keyboard())
    await cb.answer()


@dp.callback_query(F.data.startswith("delete_photo:"))
async def delete_photo(cb: types.CallbackQuery):
    telegram_id = cb.from_user.id
    user_id = user_states.get(telegram_id, {}).get("user_id")
    photo_id = int(cb.data.split(":")[1])
    result = await api_request("POST", "/profile/photo/delete", {"user_id": user_id, "photo_id": photo_id})
    if result.get("status") != "deleted":
        await cb.answer("Не удалось удалить фото", show_alert=True)
        return
    profile = await api_request("GET", f"/profile/{user_id}")
    await cb.message.answer(
        f"Фото удалено ✅\nОсталось: {len(profile.get('photos', []))}",
        reply_markup=photo_manage_keyboard(profile),
    )
    await cb.answer()


@dp.message(ProfileEdit.waiting_for_name)
async def edit_name_finish(message: types.Message, state: FSMContext):
    value = (message.text or "").strip()
    if len(value) < 2:
        await message.answer("Имя слишком короткое.")
        return
    telegram_id = message.from_user.id
    user_id = user_states.get(telegram_id, {}).get("user_id")
    await api_request("PUT", f"/profile/{user_id}", {"name": value})
    await state.clear()
    await message.answer("Имя обновлено ✅", reply_markup=main_menu())


@dp.message(ProfileEdit.waiting_for_age)
async def edit_age_finish(message: types.Message, state: FSMContext):
    try:
        age = int(message.text)
    except (TypeError, ValueError):
        await message.answer("Нужна цифра.")
        return
    if not 18 <= age <= 100:
        await message.answer("Возраст должен быть 18-100.")
        return
    telegram_id = message.from_user.id
    user_id = user_states.get(telegram_id, {}).get("user_id")
    await api_request("PUT", f"/profile/{user_id}", {"age": age})
    await state.clear()
    await message.answer("Возраст обновлен ✅", reply_markup=main_menu())


@dp.message(ProfileEdit.waiting_for_bio)
async def edit_bio_finish(message: types.Message, state: FSMContext):
    value = (message.text or "").strip()
    if len(value) < 10:
        await message.answer("Описание слишком короткое.")
        return
    telegram_id = message.from_user.id
    user_id = user_states.get(telegram_id, {}).get("user_id")
    await api_request("PUT", f"/profile/{user_id}", {"bio": value})
    await state.clear()
    await message.answer("Описание обновлено ✅", reply_markup=main_menu())


@dp.message(F.text == "💘 Смотреть анкеты")
@dp.message(Command("next"))
async def cmd_next(message: types.Message):
    telegram_id = message.from_user.id
    if telegram_id not in user_states:
        await message.answer("Сначала нажми /start.")
        return
    await api_request("POST", f"/matching/refresh/{telegram_id}")
    profile = await api_request("GET", f"/matching/next/{telegram_id}")
    if "error" in profile or "message" in profile:
        await message.answer(profile.get("message", "Не удалось загрузить анкеты."))
        return
    user_states[telegram_id]["current_profile"] = profile["id"]
    user_states[telegram_id]["current_profile_data"] = profile
    await send_profile_card(message, profile, photo_index=0)


@dp.callback_query(F.data == "pause_search")
async def pause_search(cb: types.CallbackQuery):
    await cb.message.answer("Поставил на паузу. Когда будешь готов — жми «💘 Смотреть анкеты».", reply_markup=main_menu())
    await cb.answer()


@dp.callback_query(F.data == "photo_noop")
async def photo_noop(cb: types.CallbackQuery):
    await cb.answer()


@dp.callback_query(F.data.startswith("photo_prev:") | F.data.startswith("photo_next:"))
async def navigate_photo(cb: types.CallbackQuery):
    telegram_id = cb.from_user.id
    state = user_states.get(telegram_id, {})
    profile = state.get("current_profile_data")
    if not profile or not cb.message:
        await cb.answer("Не удалось переключить фото", show_alert=True)
        return

    parts = cb.data.split(":")
    direction = parts[0]
    profile_id = int(parts[1])
    current_idx = int(parts[2])
    if profile.get("id") != profile_id:
        await cb.answer("Карточка устарела, открой новую", show_alert=True)
        return

    photos = profile.get("photos", []) or []
    photo_items = [item["file_id"] if isinstance(item, dict) else item for item in photos]
    if len(photo_items) <= 1:
        await cb.answer()
        return

    if direction == "photo_prev":
        new_idx = (current_idx - 1) % len(photo_items)
    else:
        new_idx = (current_idx + 1) % len(photo_items)

    await cb.message.edit_media(
        media=types.InputMediaPhoto(media=photo_items[new_idx], caption=profile_text(profile)),
        reply_markup=profile_keyboard(profile, new_idx),
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("like:") | F.data.startswith("skip:"))
async def process_interaction(cb: types.CallbackQuery):
    telegram_id = cb.from_user.id
    if telegram_id not in user_states:
        await cb.answer("Сессия не найдена. Нажми /start", show_alert=True)
        return

    action, profile_id = cb.data.split(":")
    result = await api_request(
        "POST",
        f"/interaction/{action}",
        {"from_telegram_id": telegram_id, "to_profile_id": int(profile_id)},
    )
    if "error" in result:
        await cb.answer("Ошибка backend", show_alert=True)
        return

    if result.get("match") and result.get("matched_profile"):
        match = result["matched_profile"]
        username = match.get("telegram_username")
        contact = f"https://t.me/{username}" if username else "username не указан"
        await cb.message.answer(
            "🎉 Взаимный лайк!\n"
            f"👤 {match.get('name', 'Пользователь')}\n"
            f"📍 {match.get('city', 'Не указан')}\n"
            f"📝 {match.get('bio', '')[:150]}\n"
            f"💬 Написать: {contact}"
        )

    next_profile = await api_request("GET", f"/matching/next/{telegram_id}")
    if "error" in next_profile or "message" in next_profile:
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.message.answer(next_profile.get("message", "Анкеты закончились."))
        await cb.answer()
        return
    user_states[telegram_id]["current_profile_data"] = next_profile
    await replace_profile_message(cb.message, next_profile)
    await cb.answer()


@dp.message(F.text == "📷 Добавить фото")
async def photo_hint(message: types.Message):
    await message.answer("Отправь фото одним сообщением. Я добавлю его в твою анкету.")


@dp.message(F.photo)
async def upload_photo(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    if telegram_id not in user_states:
        await message.answer("Сначала нажми /start, чтобы зарегистрироваться.")
        return

    file_id = message.photo[-1].file_id
    user_id = user_states[telegram_id]["user_id"]
    result = await api_request("POST", "/profile/photo/upload", {"user_id": user_id, "file_id": file_id})
    if result.get("status") == "uploaded":
        if await state.get_state() == ProfileCreation.waiting_for_photo:
            await message.answer(
                "Фото добавлено ✅ Отправь еще или нажми «Готово».",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="✅ Готово", callback_data="finish_photo_upload")]]
                ),
            )
        else:
            await message.answer("Фото добавлено в анкету ✅")
    elif result.get("status") == "exists":
        await message.answer("Это фото уже есть в анкете.")
    else:
        await message.answer(f"Не удалось добавить фото: {result.get('detail', result.get('error', 'unknown error'))}")


@dp.message(F.text == "🔄 Обновить выдачу")
@dp.message(Command("refresh"))
async def refresh_queue(message: types.Message):
    telegram_id = message.from_user.id
    result = await api_request("POST", f"/matching/refresh/{telegram_id}")
    if "error" in result:
        await message.answer(f"Не удалось обновить: {result['error']}")
    else:
        await message.answer("Выдача очищена. Нажми «💘 Смотреть анкеты».")


@dp.message()
async def fallback(message: types.Message):
    await message.answer("Используй кнопки меню ниже 👇", reply_markup=main_menu())


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в .env")
    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
