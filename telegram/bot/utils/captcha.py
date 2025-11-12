import os
import sys
from io import BytesIO
from random import choice
from string import ascii_letters, digits
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont
from captcha.image import ImageCaptcha


class Captcha:

    def __init__(self):
        self._chars = [char for char in ascii_letters + digits]
        self._count = 5
        self._width = 240
        self._height = 120

    async def random_captcha(self) -> Tuple[str, int]:
        count = self._count
        chars = self._chars
        width = self._width
        height = self._height

        image_captcha = ImageCaptcha(width, height)

        pattern = ''
        for i in range(count):
            pattern += choice(chars)

        image_captcha.write(pattern, f'src/static/captcha/{pattern}.png')
        return pattern, count

    async def create_captcha(self, chars: List = None, count: int = None, width: int = None, height: int = None):
        count = count or self._count
        chars = chars or self._chars
        width = width or self._width
        height = height or self._height

        image_captcha = ImageCaptcha(width, height)

        pattern = ''
        for i in range(count):
            pattern += choice(chars)

        captcha = image_captcha.generate(pattern)
        return captcha.read()


class NumberCaptcha:

    def __init__(self):
        self._chars = '0123456789'
        self._width = 256
        self._height = 128

    @staticmethod
    def _get_font_path() -> str:
        """Поиск доступного шрифта"""
        if sys.platform.startswith('win'):
            return "arial.ttf"
        if sys.platform == 'darwin':
            mac_fonts = [
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/System/Library/Fonts/Supplemental/Helvetica.ttf",
                "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
                "/Library/Fonts/Arial.ttf",
                "/System/Library/Fonts/NewYork.ttf",
            ]
            for font_path in mac_fonts:
                if os.path.exists(font_path):
                    return font_path
            return "Arial.ttf"
        return "DejaVuSans.ttf"

    async def random_captcha(self) -> Tuple[int, bytes]:
        first = int(choice(self._chars))
        second = int(choice(self._chars))
        captcha_font = self._get_font_path()

        result = first + second
        text = f'{first} + {second} = ?'

        image = Image.new('RGB', (self._width, self._height), (255, 255, 255))
        draw = ImageDraw.Draw(image)

        # Выберите шрифт и размер (можно использовать системный шрифт)
        try:
            font = ImageFont.truetype(captcha_font, 50)
        except OSError:
            font = ImageFont.load_default()

        # Рассчитываем размеры текста и позицию
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        text_x = (self._width - text_width) // 2
        text_y = (self._height - text_height) // 2

        # Рисуем текст на изображении
        draw.text((text_x, text_y), text, fill=(0, 0, 0), font=font)

        buffer = BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)
        return result, buffer.read()
