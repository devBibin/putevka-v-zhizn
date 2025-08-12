import logging
import os
import time
import django
import openai
from dotenv import load_dotenv
import psycopg2
from django.db import models

import config

load_dotenv()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Putevka.settings')
django.setup()

logger = logging.getLogger(__name__)

from core.models import MotivationLetter

openai.api_key = config.GPT_TOKEN

POLLING_INTERVAL = int(os.getenv("SHADOW_POLLING_INTERVAL", 60))

def get_gpt_review(letter_text):
    if not openai.api_key:
        print("Ошибка: OPENAI_API_KEY не установлен.")
        return None

    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты эксперт по оценке мотивационных писем. Напиши краткий, но информативный обзор письма, указывая его сильные и слабые стороны. Объём не более 70 слов."},
                {"role": "user", "content": f"Напиши обзор следующего мотивационного письма: {letter_text}"}
            ],
            max_tokens=300,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except openai.APIError as e:
        logger.error(f"Ошибка API OpenAI: {e}")
        return f"Ошибка генерации: {e}"
    except Exception as e:
        logger.error(f"Неизвестная ошибка при вызове GPT: {e}")
        return f"Неизвестная ошибка: {e}"

def review_unreviewed_letters():
    logger.info(f"[{time.ctime()}] Проверка непроанализированных писем...")

    letters_to_review = MotivationLetter.objects.filter(
        models.Q(gpt_review__isnull=True) | models.Q(gpt_review__exact=''),
        models.Q(admin_rating__isnull=True) | models.Q(admin_rating__exact=''),
        status=MotivationLetter.Status.SUBMITTED
    ).exclude(
        letter_text__exact=''
    )

    if not letters_to_review.exists():
        logger.info("Нет писем, требующих анализа.")
        return

    logger.info(f"Найдено {letters_to_review.count()} писем для анализа.")

    for letter in letters_to_review:
        logger.info(f"Анализ письма ID: {letter.id} от пользователя: {letter.user.username[:20]}...")
        gpt_review_text = get_gpt_review(letter.letter_text)

        if gpt_review_text:
            letter.gpt_review = gpt_review_text
            letter.save(update_fields=['gpt_review', 'updated_at'])
            logger.info(f"  -> Обзор для письма ID {letter.id} успешно сгенерирован.")
        else:
            logger.info(f"  -> Не удалось сгенерировать обзор для письма ID {letter.id}.")

def main():
    logger.info("Запуск фонового скрипта GPT Reviewer...")
    while True:
        try:
            review_unreviewed_letters()
        except Exception as e:
            logger.error(f"Критическая ошибка в главном цикле: {e}")
            logger.error("Попытка переподключения к базе данных...")
            time.sleep(30)
        logger.info(f"Следующая проверка через {POLLING_INTERVAL} секунд...")
        time.sleep(POLLING_INTERVAL)

if __name__ == "__main__":
    main()
