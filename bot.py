import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from questions import QUESTIONS
import json
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
WAITING_ANSWER = range(1)

# Хранение ответов пользователей
user_responses = {}

def get_answer_keyboard(question_num: int):
    """Создает клавиатуру с вариантами ответов"""
    keyboard = [
        [InlineKeyboardButton("1", callback_data=f"answer_{question_num}_1"),
         InlineKeyboardButton("2", callback_data=f"answer_{question_num}_2"),
         InlineKeyboardButton("3", callback_data=f"answer_{question_num}_3"),
         InlineKeyboardButton("4", callback_data=f"answer_{question_num}_4"),
         InlineKeyboardButton("5", callback_data=f"answer_{question_num}_5")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    username = update.effective_user.first_name
    
    welcome_text = (
        f"Здравствуйте, {username}!\n\n"
        "Это опросник для оценки качества жизни пациентов с хронической венозной недостаточностью (CIVIQ).\n\n"
        "Опросник состоит из 20 вопросов. На каждый вопрос нужно выбрать ответ от 1 до 5.\n\n"
        "Для начала опроса используйте команду /start_questionnaire\n"
        "Для просмотра результатов используйте команду /results\n"
        "Для начала заново используйте команду /reset"
    )
    
    await update.message.reply_text(welcome_text)
    return ConversationHandler.END


async def start_questionnaire(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает опросник"""
    user_id = update.effective_user.id
    
    # Инициализация ответов пользователя
    if user_id not in user_responses:
        user_responses[user_id] = {
            'answers': {},
            'started_at': datetime.now().isoformat(),
            'completed': False
        }
    
    # Проверка, не завершен ли уже опросник
    if user_responses[user_id]['completed']:
        await update.message.reply_text(
            "Вы уже прошли опросник. Используйте /reset для начала заново или /results для просмотра результатов."
        )
        return ConversationHandler.END
    
    # Начало с первого вопроса
    question_num = 1
    question_data = QUESTIONS[question_num]
    
    intro_text = (
        "Много людей жалуется на боли в ногах. Мы хотели бы узнать, как часто "
        "беспокоят и насколько сильно влияют данные проблемы на повседневную жизнь.\n\n"
        "Пожалуйста, укажите, испытываете ли Вы тот или иной симптом/ощущение, и, "
        "если ответ - 'да', насколько он/оно выражены. Из пяти возможных вариантов "
        "ответа выберите наиболее подходящий.\n\n"
        "1 - если симптомы не относятся к Вам\n"
        "2, 3, 4 или 5 - если Вы ощущали симптомы в той или иной степени\n\n"
        f"Вопрос {question_num} из {len(QUESTIONS)}:\n\n"
        f"{question_data['text']}\n\n"
        f"{question_data['options']}"
    )
    
    await update.message.reply_text(
        intro_text,
        reply_markup=get_answer_keyboard(question_num)
    )
    
    return WAITING_ANSWER


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ответ пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Парсинг данных из callback
    _, question_num, answer = query.data.split('_')
    question_num = int(question_num)
    answer = int(answer)
    
    # Сохранение ответа
    if user_id not in user_responses:
        user_responses[user_id] = {
            'answers': {},
            'started_at': datetime.now().isoformat(),
            'completed': False
        }
    
    user_responses[user_id]['answers'][question_num] = answer
    
    # Проверка, есть ли еще вопросы
    if question_num < len(QUESTIONS):
        # Переход к следующему вопросу
        next_question_num = question_num + 1
        question_data = QUESTIONS[next_question_num]
        
        question_text = (
            f"Вопрос {next_question_num} из {len(QUESTIONS)}:\n\n"
            f"{question_data['text']}\n\n"
            f"{question_data['options']}"
        )
        
        await query.edit_message_text(
            question_text,
            reply_markup=get_answer_keyboard(next_question_num)
        )
        
        return WAITING_ANSWER
    else:
        # Опросник завершен
        user_responses[user_id]['completed'] = True
        user_responses[user_id]['completed_at'] = datetime.now().isoformat()
        
        # Подсчет результатов
        results = calculate_results(user_id)
        
        completion_text = (
            "Спасибо! Вы завершили опросник.\n\n"
            f"Ваши результаты:\n"
            f"Общий балл: {results['total_score']} из {results['max_score']}\n"
            f"Процент: {results['percentage']:.1f}%\n\n"
            "Используйте /results для подробного просмотра результатов."
        )
        
        await query.edit_message_text(completion_text)
        
        # Сохранение результатов в файл
        save_results_to_file(user_id)
        
        return ConversationHandler.END


def calculate_results(user_id: int) -> dict:
    """Подсчитывает результаты опросника"""
    if user_id not in user_responses or not user_responses[user_id]['completed']:
        return {'total_score': 0, 'max_score': 0, 'percentage': 0}
    
    answers = user_responses[user_id]['answers']
    total_score = sum(answers.values())
    max_score = len(QUESTIONS) * 5  # Максимальный балл (20 вопросов * 5)
    percentage = (total_score / max_score) * 100 if max_score > 0 else 0
    
    return {
        'total_score': total_score,
        'max_score': max_score,
        'percentage': percentage
    }


def save_results_to_file(user_id: int):
    """Сохраняет результаты в JSON файл"""
    if user_id not in user_responses:
        return
    
    filename = f"results_{user_id}.json"
    filepath = os.path.join(os.path.dirname(__file__), filename)
    
    results_data = {
        'user_id': user_id,
        'responses': user_responses[user_id],
        'calculated_results': calculate_results(user_id)
    }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(results_data, f, ensure_ascii=False, indent=2)


async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает результаты опросника"""
    user_id = update.effective_user.id
    
    if user_id not in user_responses or not user_responses[user_id].get('completed'):
        await update.message.reply_text(
            "Вы еще не прошли опросник. Используйте /start_questionnaire для начала."
        )
        return
    
    results = calculate_results(user_id)
    answers = user_responses[user_id]['answers']
    
    results_text = f"Ваши результаты опросника CIVIQ:\n\n"
    results_text += f"Общий балл: {results['total_score']} из {results['max_score']}\n"
    results_text += f"Процент: {results['percentage']:.1f}%\n\n"
    results_text += "Ответы по вопросам:\n\n"
    
    for q_num in sorted(answers.keys()):
        question_data = QUESTIONS[q_num]
        answer = answers[q_num]
        results_text += f"Вопрос {q_num}: {answer}/5\n"
        results_text += f"  {question_data['text'][:50]}...\n\n"
    
    await update.message.reply_text(results_text)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сбрасывает результаты пользователя"""
    user_id = update.effective_user.id
    
    if user_id in user_responses:
        del user_responses[user_id]
    
    await update.message.reply_text(
        "Ваши результаты сброшены. Используйте /start_questionnaire для начала нового опроса."
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет текущий опросник"""
    await update.message.reply_text(
        "Опросник отменен. Используйте /start_questionnaire для начала заново."
    )
    return ConversationHandler.END


def main() -> None:
    """Запускает бота"""
    # Получение токена из переменной окружения
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не установлен!")
        print("Пожалуйста, установите переменную окружения TELEGRAM_BOT_TOKEN")
        return
    
    # Создание приложения
    application = Application.builder().token(token).build()
    
    # Создание ConversationHandler для опросника
    questionnaire_handler = ConversationHandler(
        entry_points=[CommandHandler('start_questionnaire', start_questionnaire)],
        states={
            WAITING_ANSWER: [CallbackQueryHandler(handle_answer, pattern=r'^answer_\d+_[1-5]$')],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler('start', start))
    application.add_handler(questionnaire_handler)
    application.add_handler(CommandHandler('results', show_results))
    application.add_handler(CommandHandler('reset', reset))
    
    # Запуск бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

