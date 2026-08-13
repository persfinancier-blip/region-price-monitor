#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Единый скрипт для парсинга цен Ozon с автоматическим решением капчи.
Использует прокси, решает слайдер, сохраняет куки, затем парсит цены.
"""

import json
import os
import sys
import base64
import re
from io import BytesIO
from typing import Optional, Dict, Any, Tuple

import cv2
import numpy as np
from PIL import Image
from curl_cffi import requests

# ------------------------------------------------------------
# 1. Вспомогательные функции для работы с прокси и сессией
# ------------------------------------------------------------

def create_session(proxy: Optional[str] = None, impersonate: str = "chrome") -> requests.Session:
    """Создаёт сессию curl_cffi с возможностью прокси."""
    session = requests.Session(impersonate=impersonate)
    if proxy:
        # формат proxy: http://user:pass@host:port
        session.proxies = {"http": proxy, "https": proxy}
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Origin": "https://www.ozon.ru",
        "Referer": "https://www.ozon.ru/",
    })
    return session


def save_cookies(session: requests.Session, filename: str = "cookies.json"):
    """Сохраняет куки сессии в JSON-файл."""
    cookies = session.cookies.get_dict()
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    print(f"[COOKIES] Saved to {filename}")


def load_cookies(session: requests.Session, filename: str = "cookies.json") -> bool:
    """Загружает куки из JSON-файла в сессию."""
    if not os.path.exists(filename):
        return False
    with open(filename, "r", encoding="utf-8") as f:
        cookies = json.load(f)
    session.cookies.update(cookies)
    print(f"[COOKIES] Loaded from {filename}")
    return True


# ------------------------------------------------------------
# 2. Алгоритм решения капчи-слайдера (реализация из проекта)
# ------------------------------------------------------------

def decode_captcha_url(captcha_url: str) -> Dict[str, str]:
    """
    Декодирует URL капчи, извлекая ссылки на изображения.
    В Ozon captchaURL содержит закодированные параметры, которые нужно расшифровать.
    Эта функция эмулирует работу оригинальной decode_captcha_url из репозитория.
    """
    # Пример captchaURL:
    # https://www.ozon.ru/captcha/challenge?c=...&b=...&p=...
    # Параметры b и p могут быть закодированы в base64.
    # В реальном проекте используется более сложное декодирование.
    # Здесь мы попытаемся извлечь прямые ссылки, если они есть.
    if "image_url" in captcha_url or "puzzle_url" in captcha_url:
        # Если уже есть прямые ссылки – извлекаем
        # (на самом деле Ozon редко даёт прямые ссылки, чаще параметры)
        pass

    # Если ссылки не прямые, пробуем декодировать параметры.
    # В большинстве случаев параметр 'c' содержит challenge ID, 'b' – background, 'p' – puzzle.
    # Для простоты мы вернём заглушку, которую нужно заменить на реальную логику.
    # ВАЖНО: для работоспособности нужно скопировать функцию decode_captcha_url
    # из оригинального репозитория (captcha/ozon_payload.py).
    # Пока вернём фиктивные ссылки – они вызовут ошибку, но покажут структуру.
    # Вы можете заменить этот блок на реальный код.

    # Пример реальной реализации (упрощённо):
    # Извлекаем параметры b и p, декодируем base64, получаем URLs
    # Но для демонстрации я сгенерирую URL на основе captcha_url.
    # Замените этот код на правильный.
    print("[WARN] Используется заглушка decode_captcha_url. Замените на реальную функцию.")
    # Допустим, в captcha_url есть параметры
    return {
        "image_url": captcha_url + "&image=background",
        "puzzle_url": captcha_url + "&image=puzzle"
    }


def solve_piece_by_contour(background: bytes, puzzle: bytes) -> Tuple[int, int, float]:
    """
    Решает слайдер по контурам (алгоритм из проекта).
    Возвращает (x, y, confidence).
    """
    # Конвертируем байты в изображения OpenCV
    bg_img = cv2.imdecode(np.frombuffer(background, np.uint8), cv2.IMREAD_COLOR)
    pzl_img = cv2.imdecode(np.frombuffer(puzzle, np.uint8), cv2.IMREAD_COLOR)

    if bg_img is None or pzl_img is None:
        raise ValueError("Не удалось декодировать изображения")

    # 1. Находим контуры на пазле (обычно это прозрачная область)
    gray_pzl = cv2.cvtColor(pzl_img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray_pzl, 1, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        # Если не нашли, пробуем другой метод
        return (bg_img.shape[1] // 2, bg_img.shape[0] // 2, 0.5)

    # Берём самый большой контур
    c = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(c)
    center_x = x + w // 2
    center_y = y + h // 2
    confidence = float(w * h) / (bg_img.shape[0] * bg_img.shape[1])
    return (center_x, center_y, confidence)


# ------------------------------------------------------------
# 3. Основная логика работы с капчей и парсингом
# ------------------------------------------------------------

def solve_captcha(session: requests.Session, sku: str) -> bool:
    """
    Выполняет полный цикл решения капчи:
    - запрос к API Ozon,
    - если есть captchaURL – решает и отправляет,
    - сохраняет куки.
    Возвращает True, если капча успешно решена (или не требовалась).
    """
    print(f"[1/4] Запрос к Ozon для SKU={sku} ...")
    api_url = "https://www.ozon.ru/api/composer-api.bx/_action/product"
    headers = {
        "Referer": f"https://www.ozon.ru/product/{sku}/",
        "Content-Type": "application/json",
    }
    params = {"url": f"/product/{sku}/"}
    try:
        resp = session.get(api_url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Ошибка запроса: {e}")
        return False

    data = resp.json()
    captcha_url = data.get("captchaURL")
    if not captcha_url:
        print("[OK] Капча не требуется, данные получены.")
        save_cookies(session)
        return True

    print("[2/4] Обнаружена капча, начинаем решение...")
    # Декодируем URL капчи
    try:
        decoded = decode_captcha_url(captcha_url)
    except Exception as e:
        print(f"[ERROR] Не удалось декодировать captchaURL: {e}")
        return False

    # Скачиваем изображения
    print("[3/4] Скачивание изображений...")
    try:
        bg_resp = session.get(decoded["image_url"], timeout=30)
        bg_resp.raise_for_status()
        puzzle_resp = session.get(decoded["puzzle_url"], timeout=30)
        puzzle_resp.raise_for_status()
        bg_bytes = bg_resp.content
        puzzle_bytes = puzzle_resp.content
    except Exception as e:
        print(f"[ERROR] Ошибка загрузки изображений: {e}")
        return False

    # Решаем слайдер
    print("[4/4] Решение слайдера...")
    try:
        x, y, confidence = solve_piece_by_contour(bg_bytes, puzzle_bytes)
        print(f"      Результат: x={x}, y={y}, уверенность={confidence:.3f}")
    except Exception as e:
        print(f"[ERROR] Ошибка при решении слайдера: {e}")
        return False

    # Отправляем решение
    submit_url = "https://www.ozon.ru/api/composer-api.bx/_action/abt/captcha/result"
    challenge_id = data.get("challengeId") or data.get("id")
    if not challenge_id:
        print("[ERROR] Не найден challengeId в ответе.")
        return False

    payload = {
        "challengeId": challenge_id,
        "x": x,
        "y": y,
    }
    for key in ("token", "signature"):
        if key in data:
            payload[key] = data[key]

    try:
        sub_resp = session.post(submit_url, json=payload, headers=headers, timeout=30)
        sub_resp.raise_for_status()
        sub_data = sub_resp.json()
        if sub_data.get("success") or sub_data.get("result") == "ok":
            print("[SUCCESS] Капча успешно решена и отправлена!")
            save_cookies(session)
            return True
        else:
            print(f"[ERROR] Ошибка при отправке решения: {sub_data}")
            return False
    except Exception as e:
        print(f"[ERROR] Ошибка при отправке: {e}")
        return False


def parse_price(session: requests.Session, sku: str) -> Optional[float]:
    """
    Парсит цену товара по SKU, используя переданную сессию (с куками).
    Возвращает цену в виде float или None.
    """
    api_url = "https://www.ozon.ru/api/composer-api.bx/_action/product"
    params = {"url": f"/product/{sku}/"}
    headers = {"Referer": f"https://www.ozon.ru/product/{sku}/"}
    try:
        resp = session.get(api_url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # Цена может быть в разных местах
        price = data.get("price")
        if price is None:
            offers = data.get("offers")
            if offers and isinstance(offers, list) and len(offers) > 0:
                price = offers[0].get("price")
        if price is not None:
            return float(price)
        else:
            print("[WARN] Цена не найдена в ответе.")
            return None
    except Exception as e:
        print(f"[ERROR] Ошибка при парсинге цены: {e}")
        return None


# ------------------------------------------------------------
# 4. Главная функция
# ------------------------------------------------------------

def main():
    print("=== Ozon Parser with Auto Captcha Solver ===\n")

    proxy_raw = input("Введите прокси (формат: http://user:pass@host:port или оставьте пустым): ").strip()
    proxy_str = proxy_raw if proxy_raw else None

    sku = input("Введите SKU товара (например, 3129447770): ").strip()
    if not sku:
        sku = "3129447770"
        print(f"Используем SKU по умолчанию: {sku}")

    session = create_session(proxy=proxy_str)

    # Пытаемся загрузить сохранённые куки
    if load_cookies(session):
        print("[INFO] Куки загружены, пробуем парсинг без решения капчи.")
        price = parse_price(session, sku)
        if price is not None:
            print(f"[RESULT] Цена товара {sku}: {price} руб.")
            return

    # Если куки не помогли или их нет – решаем капчу
    print("[INFO] Запускаем процесс решения капчи...")
    if not solve_captcha(session, sku):
        print("[ERROR] Не удалось решить капчу. Выход.")
        sys.exit(1)

    # После успешного решения пробуем парсить цену
    print("[INFO] Парсинг цены...")
    price = parse_price(session, sku)
    if price is not None:
        print(f"[RESULT] Цена товара {sku}: {price} руб.")
    else:
        print("[ERROR] Не удалось получить цену даже после решения капчи.")


if __name__ == "__main__":
    main()