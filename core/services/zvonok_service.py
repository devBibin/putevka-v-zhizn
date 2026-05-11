import logging

import requests

from Putevka import settings

import config

logger = logging.getLogger(__name__)


def initiate_zvonok_verification(phone, pincode=None):
    url = config.ZVONOK_API_INITIATE_URL
    data = {
        'public_key': config.PUBLIC_KEY_CALL,
        'phone': phone,
        'campaign_id': config.CAMPAIGN_ID,
    }
    if pincode:
        data['pincode'] = pincode

    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP-ошибка при вызове API zvonok.com (initiate): {e.response.status_code} - {e.response.text}")
        return {
            "status": "error",
            "message": f"Ошибка сервиса звонков: {e.response.status_code}. Пожалуйста, попробуйте позже."
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка подключения при вызове API zvonok.com (initiate): {e}")
        return {
            "status": "error",
            "message": "Не удалось подключиться к сервису звонков. Пожалуйста, проверьте интернет-соединение или попробуйте позже."
        }
    except Exception as e:
        logger.error(f"Непредвиденная ошибка в initiate_zvonok_verification: {e}")
        return {
            "status": "error",
            "message": "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
        }


def poll_zvonok_status(phone):
    url = config.ZVONOK_API_POLLING_URL
    params = {
        'public_key': config.PUBLIC_KEY_CALL,
        'phone': phone,
        'campaign_id': config.CAMPAIGN_ID
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json() if (isinstance(response.json(), dict)) else response.json()[0]
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при вызове API zvonok.com (polling): {e}")
        return None
