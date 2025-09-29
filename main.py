import asyncio
import os
import whisper 
from moviepy import VideoFileClip 
from dotenv import load_dotenv
from deep_translator import GoogleTranslator

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Загружаем переменные окружения из .env файла
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# --- ЗАГРУЗКА МОДЕЛИ WHISPER ---
print("Загрузка модели Whisper...")
model = whisper.load_model("base")
print("Модель Whisper загружена.")

# --- ОПРЕДЕЛЕНИЕ СОСТОЯНИЙ ---
# Создаем класс для хранения состояний нашего бота
class TranscriptionStates(StatesGroup):
    WaitingForLanguageChoice = State()

# Инициализируем бота и диспетчер
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- СОЗДАНИЕ КЛАВИАТУРЫ (КНОПОК) ---
# Создаем кнопки один раз, чтобы переиспользовать их
language_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
        InlineKeyboardButton(text="🇪🇸 Español", callback_data="lang_es")
    ]
])


# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ---

@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    """ Обработчик команды /start """
    await message.reply(
        "Привет!\nЯ готов транскрибировать и переводить видео.\n\n"
        "Просто отправь мне видеофайл."
    )

@dp.message(F.video)
async def handle_video(message: types.Message, state: FSMContext):
    """
    Этот обработчик срабатывает при получении видео.
    Он не транскрибирует, а только спрашивает язык.
    """
    # --- ДОБАВЛЕНА ПРОВЕРКА РАЗМЕРА ФАЙЛА ---
    # 20 * 1024 * 1024 = 20 MB в байтах
    if message.video.file_size > 20 * 1024 * 1024:
        await message.reply("❌ Этот файл слишком большой.\nЯ могу обрабатывать видео размером до 20 МБ.")
        return # Останавливаем выполнение функции
    # -----------------------------------------
    # Сохраняем ID файла в "память" состояния, чтобы использовать его позже
    await state.update_data(video_file_id=message.video.file_id)
    
    # Задаем вопрос и прикрепляем клавиатуру с кнопками
    await message.reply("На каком языке речь в видео?", reply_markup=language_keyboard)
    
    # Переводим пользователя в состояние ожидания выбора языка
    await state.set_state(TranscriptionStates.WaitingForLanguageChoice)

@dp.callback_query(TranscriptionStates.WaitingForLanguageChoice)
async def process_language_choice(callback: types.CallbackQuery, state: FSMContext):
    """
    Этот обработчик срабатывает, когда пользователь нажимает на одну из кнопок.
    Здесь происходит вся основная работа.
    """
    # Получаем язык из данных кнопки (например, 'lang_en' -> 'en')
    lang = callback.data.split('_')[1]
    
    # Получаем ID файла, который мы сохранили ранее
    user_data = await state.get_data()
    file_id = user_data.get('video_file_id')
    
    # Отвечаем на нажатие кнопки, чтобы у пользователя пропали "часики"
    await callback.answer()
    
    # Редактируем сообщение, убирая кнопки и показывая, что работа началась
    await callback.message.edit_text(f"Принято: '{lang}'. Начинаю обработку...")

    video_path = None
    audio_path = None
    try:
        # --- Дальше идет уже знакомая нам логика ---
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        video_path = f"downloads/{file_id}.mp4"
        audio_path = f"downloads/{file_id}.mp3"
        os.makedirs('downloads', exist_ok=True)
        
        await bot.download_file(file_path, destination=video_path)
        
        video_clip = VideoFileClip(video_path)
        video_clip.audio.write_audiofile(audio_path, logger=None) # logger=None чтобы не было лишнего вывода
        video_clip.close()
        
        result = model.transcribe(audio_path, language=lang)
        transcribed_text = result["text"]

        if not transcribed_text.strip():
            await callback.message.edit_text("Не удалось распознать речь в видео.")
            return

        translator = GoogleTranslator(source=lang, target='ru')
        translated_text = translator.translate(transcribed_text)
        
        response_text = (
            f"**Оригинал ({lang}):**\n{transcribed_text}\n\n"
            f"**Перевод (ru):**\n{translated_text}"
        )
        await callback.message.edit_text(response_text) # Редактируем сообщение с результатом
        
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        await callback.message.edit_text("Произошла ошибка при обработке видео.")
    finally:
        # Очищаем временные файлы
        if video_path and os.path.exists(video_path): os.remove(video_path)
        if audio_path and os.path.exists(audio_path): os.remove(audio_path)
        # Выходим из состояния, завершая диалог
        await state.clear()


# --- ЗАПУСК БОТА ---
async def main() -> None:
    await dp.start_polling(bot)

if __name__ == "__main__":
    print("Бот запущен!")
    asyncio.run(main())