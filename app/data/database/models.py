import json
import logging
import sqlite3
from datetime import date, datetime
from random import randint
from typing import Optional
import aiosqlite

# help_defs импортируется локально в методах для избежания циклических зависимостей
from telegraph import Telegraph

telegraph = Telegraph()
logger = logging.getLogger()


class Customer:
    def __init__(self, id: int | None, tg_id: int, city_id: int, tg_name: str, abs_count: int = None,
                 access_token: str = None, author_name: str = None,
                 contact_type: str = None, phone_number: str = None):
        self.id = id
        self.tg_id = tg_id
        self.city_id = city_id
        self.tg_name = tg_name
        self.abs_count = abs_count
        self.access_token = access_token
        self.author_name = author_name
        self.contact_type = contact_type
        self.phone_number = phone_number

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            # Асинхронно создаем аккаунт Telegraph с таймаутом
            import asyncio
            try:
                # Выполняем синхронный вызов в отдельном потоке с таймаутом
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        telegraph.create_account,
                        f'customer_{self.tg_id}',
                        'haltura customer',
                        'https://t.me/Rus_haltura_bot'
                    ),
                    timeout=10.0  # Таймаут 10 секунд
                )
                access_token = result['access_token']
                author_name = result['author_name']
            except asyncio.TimeoutError:
                # Если Telegraph API недоступен, используем значения по умолчанию
                access_token = f'customer_{self.tg_id}_default'
                author_name = 'haltura customer'
            except Exception as e:
                # В случае любой другой ошибки, используем значения по умолчанию
                access_token = f'customer_{self.tg_id}_default'
                author_name = 'haltura customer'

            cursor = await conn.execute(
                'INSERT INTO customers (tg_id, city_id, tg_name, access_token, author_name) VALUES (?, ?, ?, ?, ?)',
                (self.tg_id, self.city_id, self.tg_name, access_token, author_name))
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_customer(cls, id: int = None, tg_id: int = None) -> Optional['Customer'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            if id:
                cursor = await conn.execute('SELECT * FROM customers WHERE id = ?', [id])
            else:
                cursor = await conn.execute('SELECT * FROM customers WHERE tg_id = ?', [tg_id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(id=record[0], city_id=record[1], tg_id=record[2], tg_name=record[3], abs_count=record[4],
                           access_token=record[5], author_name=record[6],
                           contact_type=record[7] if len(record) > 7 else None,
                           phone_number=record[8] if len(record) > 8 else None)
            else:
                return None
        finally:
            await conn.close()

    async def create_telegra_login(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            result = telegraph.create_account(short_name=f'customer_{self.tg_id}', author_name='haltura customer',
                                              author_url='https://t.me/Rus_haltura_bot')
            query = 'UPDATE customers SET access_token = ?, author_name =? WHERE id = ?'
            params = (result['access_token'], result['author_name'], self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all_in_city(cls, city_id: int) -> list['Customer'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM customers WHERE city_id = ?', [city_id])
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(id=record[0], city_id=record[1], tg_id=record[2], tg_name=record[3], abs_count=record[4],
                            access_token=record[5], author_name=record[6],
                            contact_type=record[7] if len(record) > 7 else None,
                            phone_number=record[8] if len(record) > 8 else None)
                        for record in records]
            else:
                return None
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['Customer']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM customers')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0], city_id=record[1], tg_id=record[2], tg_name=record[3], abs_count=record[4],
                        access_token=record[5], author_name=record[6],
                        contact_type=record[7] if len(record) > 7 else None,
                        phone_number=record[8] if len(record) > 8 else None) for
                    record in records]
        finally:
            await conn.close()

    async def update_contacts(self, contact_type: str = None, phone_number: str = None) -> None:
        """Обновляет контакты заказчика"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            if self.id:
                cursor = await conn.execute(
                    'UPDATE customers SET contact_type = ?, phone_number = ? WHERE id = ?',
                    [contact_type, phone_number, self.id]
                )
            else:
                cursor = await conn.execute(
                    'UPDATE customers SET contact_type = ?, phone_number = ? WHERE tg_id = ?',
                    [contact_type, phone_number, self.tg_id]
                )
            await conn.commit()
            await cursor.close()
            
            # Обновляем объект
            self.contact_type = contact_type
            self.phone_number = phone_number
        finally:
            await conn.close()

    def get_contact_info(self) -> str:
        """Возвращает информацию о контактах заказчика для отображения"""
        if not self.contact_type:
            return "Контакты не настроены"
        
        if self.contact_type == "telegram_only":
            return f"📱 [Профиль Telegram](tg://user?id={self.tg_id}) (@{self.tg_name})"
        elif self.contact_type == "phone_only":
            return f"📞 [Номер телефона](tel:{self.phone_number}) - {self.phone_number}"
        elif self.contact_type == "both":
            return f"📱 [Профиль Telegram](tg://user?id={self.tg_id}) (@{self.tg_name})\n📞 [Номер телефона](tel:{self.phone_number}) - {self.phone_number}"
        else:
            return "Контакты не настроены"

    def has_contacts(self) -> bool:
        """Проверяет, настроены ли контакты заказчика"""
        return self.contact_type is not None

    async def delete(self) -> None:
        if self.id or self.tg_id:
            conn = await aiosqlite.connect(database='app/data/database/database.db')
            try:
                cursor = await conn.execute('DELETE FROM customers WHERE id = ?', [self.id])
                await conn.commit()
                await cursor.close()
            finally:
                await conn.close()

    async def update_city(self, city_id: int) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE customers SET city_id = ? WHERE id = ?'
            params = (city_id, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update_abs_count(self, abs_count: int) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE customers SET abs_count = ? WHERE id = ?'
            params = (abs_count, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def count(cls) -> int:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT COUNT(1) FROM customers')
            record = await cursor.fetchone()
            await cursor.close()
            return int(record[0]) if record else 0
        finally:
            await conn.close()


class Worker:
    def __init__(self, tg_id: int, city_id: list,
                 tg_name: str, registration_data: str, ref_code: str = None,
                 confirmed: bool = False, stars: int = 0, count_ratings: int = 0,
                 order_count_on_week: int = 0,
                 order_count: int = 0, id: int = None, phone_number: str = None,
                 confirmation_code: str = None, active: bool = True,
                 access_token: str = None, author_name: str = None,
                 individual_entrepreneur: bool = False,
                 profile_photo: str = None,
                 profile_name: str = None,
                 portfolio_photo: dict = None,
                 purchased_contacts: int = 0,
                 unlimited_contacts_until: str = None,
                 activity_level: int = 100,
                 name_violations_count: int = 0):
        self.id = id
        self.tg_id = tg_id
        self.tg_name = tg_name
        self.phone_number = phone_number
        self.city_id = city_id
        self.confirmed = confirmed
        self.stars = stars
        self.count_ratings = count_ratings
        self.order_count = order_count
        self.order_count_on_week = order_count_on_week
        if confirmation_code is not None:
            self.confirmation_code = confirmation_code
        else:
            self.confirmation_code = randint(1000, 9999)
        self.ref_code = tg_id
        self.active = active
        self.access_token = access_token
        self.author_name = author_name
        self.individual_entrepreneur = individual_entrepreneur
        self.registration_data = registration_data
        self.profile_photo = profile_photo
        self.profile_name = profile_name
        self.portfolio_photo = portfolio_photo
        self.purchased_contacts = purchased_contacts
        self.unlimited_contacts_until = unlimited_contacts_until
        self.activity_level = activity_level
        self.name_violations_count = name_violations_count

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            city_id = [str(x) for x in self.city_id]
            city_id = ' | '.join(city_id)

            cursor = await conn.execute(
                'INSERT INTO workers (tg_id, tg_name, city_id, phone_number, confirmation_code, ref_code, registration_data, profile_name, purchased_contacts, unlimited_contacts_until, activity_level, name_violations_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (self.tg_id, self.tg_name, city_id, self.phone_number, self.confirmation_code, self.tg_id,
                 self.registration_data, self.profile_name, self.purchased_contacts, self.unlimited_contacts_until,
                 self.activity_level, self.name_violations_count))
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_worker(cls, id: int = None, tg_id: int = None, ref_code: int = None) -> Optional['Worker']:
        if id or tg_id:
            conn = await aiosqlite.connect(database='app/data/database/database.db')
            try:
                if id:
                    cursor = await conn.execute('SELECT * FROM workers WHERE id = ?', [id])
                elif tg_id:
                    cursor = await conn.execute('SELECT * FROM workers WHERE tg_id = ?', [tg_id])
                else:
                    cursor = await conn.execute('SELECT * FROM workers WHERE ref_code = ?', [ref_code])
                record = await cursor.fetchone()
                await cursor.close()
                if record:
                    return cls(
                        id=record[0],
                        tg_id=record[1],
                        tg_name=record[2],
                        phone_number=record[3],
                        city_id=[int(x) for x in record[4].split(' | ')],
                        confirmed=True if record[5] else False,
                        stars=record[6],
                        count_ratings=record[7],
                        order_count=record[8],
                        order_count_on_week=record[9],
                        confirmation_code=record[10],
                        ref_code=record[11],
                        active=True if record[12] == 1 else False,
                        access_token=record[13],
                        author_name=record[14],
                        individual_entrepreneur=True if record[15] == 1 else False,
                        registration_data=record[16],
                        profile_photo=record[17],
                        profile_name=record[18],
                        portfolio_photo=json.loads(record[19]) if record[19] else None,
                        purchased_contacts=record[20] if len(record) > 20 else 0,
                        unlimited_contacts_until=record[21] if len(record) > 21 else None,
                        activity_level=record[22] if len(record) > 22 else 100,
                        name_violations_count=record[23] if len(record) > 23 else 0
                    )
                else:
                    return None
            finally:
                await conn.close()
        else:
            return None

    @classmethod
    async def get_all_in_city(cls, city_id: int) -> list['Worker'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM workers')
            records = await cursor.fetchall()
            await cursor.close()

            if records:
                matching_records = []
                city_id_str = str(city_id)
                for record in records:
                    record_city_ids = record[4].split(' | ')
                    if city_id_str in record_city_ids:
                        worker = cls(
                            id=record[0],
                            tg_id=record[1],
                            tg_name=record[2],
                            phone_number=record[3],
                            city_id=[int(x) for x in record_city_ids],  # Преобразуем каждый city_id в int
                            confirmed=record[5],
                            stars=record[6],
                            count_ratings=record[7],
                            order_count=record[8],
                            order_count_on_week=record[9],
                            confirmation_code=record[10],
                            ref_code=record[11],
                            active=True if record[12] == 1 else False,
                            access_token=record[13],
                            author_name=record[14],
                            individual_entrepreneur=True if record[15] == 1 else False,
                            registration_data=record[16],
                            profile_photo=record[17],
                            profile_name=record[18],
                            portfolio_photo=json.loads(record[19]) if record[19] else None,
                            purchased_contacts=record[20] if len(record) > 20 else 0,
                            unlimited_contacts_until=record[21] if len(record) > 21 else None,
                            activity_level=record[22] if len(record) > 22 else 100,
                            name_violations_count=record[23] if len(record) > 23 else 0
                        )
                        matching_records.append(worker)

                return matching_records if matching_records else None
            else:
                return None
        finally:
            await conn.close()

    @classmethod
    async def get_active_workers_for_advertisement(cls, city_id: int, work_type_id: int) -> list['Worker']:
        """
        Получение активных исполнителей по городу и типу работы.
        Учитывает основной город из workers.city_id и дополнительные города из worker_city_subscriptions
        ОПТИМИЗИРОВАНО: один запрос вместо N запросов для каждого воркера
        """
        import logging
        logger = logging.getLogger()
        logger.debug(f'[OPTIMIZED] get_active_workers_for_advertisement: city_id={city_id}, work_type_id={work_type_id}')

        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            # Оптимизированный запрос: получаем всех воркеров с их подписками одним запросом
            # GROUP_CONCAT агрегирует все подписки для каждого воркера
            # Используем запятую как разделитель в GROUP_CONCAT, так как city_ids внутри уже содержит |
            query = '''
                    SELECT 
                        w.*, 
                        ws.work_type_ids,
                        GROUP_CONCAT(wcs.city_ids) as subscription_cities
                    FROM workers w
                    LEFT JOIN worker_and_subscription ws ON w.id = ws.worker_id
                    LEFT JOIN worker_city_subscriptions wcs ON w.id = wcs.worker_id AND wcs.active = 1
                    WHERE w.active = 1
                    GROUP BY w.id
                    '''
            cursor = await conn.execute(query)
            records = await cursor.fetchall()
            await cursor.close()

            logger.debug(f'[OPTIMIZED] Found {len(records)} active workers in database')

            matching_workers = []
            work_type_id_str = str(work_type_id)
            city_id_str = str(city_id)

            for record in records:
                # Проверяем основной город (формат: "1 | 2 | 3")
                try:
                    main_city_str = str(record[4]) if record[4] is not None else ''
                    main_city_ids = [cid.strip() for cid in main_city_str.split(' | ') if cid.strip()] if main_city_str else []
                except (AttributeError, TypeError):
                    continue

                # Получаем дополнительные города из подписок (уже агрегированы в запросе)
                # GROUP_CONCAT объединяет строки через запятую по умолчанию
                # Каждая подписка содержит city_ids в формате "1|2|3"
                subscription_cities_str = record[25] if len(record) > 25 and record[25] else ''
                additional_city_ids = []
                if subscription_cities_str:
                    # GROUP_CONCAT объединяет через запятую: "1|2|3,4|5,6|7|8"
                    # Сначала разбиваем по запятой, потом каждый элемент по |
                    subscription_list = subscription_cities_str.split(',')
                    for sub_cities in subscription_list:
                        if sub_cities:
                            # Каждая подписка может содержать несколько городов через |
                            cities = sub_cities.split('|')
                            additional_city_ids.extend([cid.strip() for cid in cities if cid.strip()])
                    # Убираем дубликаты
                    additional_city_ids = list(dict.fromkeys(additional_city_ids))

                # Объединяем основной город и дополнительные города
                all_city_ids = main_city_ids + additional_city_ids

                # Проверяем, есть ли нужный город в списке всех городов
                if city_id_str not in all_city_ids:
                    continue

                # Проверяем тип работы (work_type_ids из таблицы worker_and_subscription)
                try:
                    work_type_ids_str = str(record[24]) if len(record) > 24 and record[24] is not None else ''
                    work_type_ids = [id.strip() for id in work_type_ids_str.split('|') if id.strip()] if work_type_ids_str else []
                except (AttributeError, TypeError, IndexError):
                    work_type_ids = []

                # Проверяем тип работы
                # Если work_type_ids=['0'] - это безлимитная подписка (получает все типы)
                # Если work_type_ids пустой - тоже получает все типы
                # Если есть конкретные типы - проверяем совпадение
                is_unlimited = len(work_type_ids) == 1 and work_type_ids[0] == '0'

                if work_type_ids and not is_unlimited and work_type_id_str not in work_type_ids:
                    continue

                # Создаем объект воркера
                worker = cls(
                    id=record[0],
                    tg_id=record[1],
                    tg_name=record[2],
                    phone_number=record[3],
                    city_id=[int(x) for x in all_city_ids if x],
                    confirmed=record[5],
                    stars=record[6],
                    count_ratings=record[7],
                    order_count=record[8],
                    order_count_on_week=record[9],
                    confirmation_code=record[10],
                    ref_code=record[11],
                    active=True if record[12] == 1 else False,
                    access_token=record[13],
                    author_name=record[14],
                    individual_entrepreneur=True if record[15] == 1 else False,
                    registration_data=record[16],
                    profile_photo=record[17],
                    profile_name=record[18],
                    portfolio_photo=json.loads(record[19]) if record[19] else None,
                    purchased_contacts=record[20] if len(record) > 20 else 0,
                    unlimited_contacts_until=record[21] if len(record) > 21 else None,
                    activity_level=record[22] if len(record) > 22 else 100,
                    name_violations_count=record[23] if len(record) > 23 else 0
                )
                matching_workers.append(worker)

            logger.debug(f'[OPTIMIZED] Final result: {len(matching_workers)} matching workers found')
            return matching_workers
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['Worker']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM workers')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(
                id=record[0],
                tg_id=record[1],
                tg_name=record[2],
                phone_number=record[3],
                city_id=[int(x) for x in record[4].split(' | ')],
                confirmed=record[5],
                stars=record[6],
                count_ratings=record[7],
                order_count=record[8],
                order_count_on_week=record[9],
                confirmation_code=record[10],
                ref_code=record[11],
                active=True if record[12] == 1 else False,
                access_token=record[13],
                author_name=record[14],
                individual_entrepreneur=True if record[15] == 1 else False,
                registration_data=record[16],
                profile_photo=record[17],
                profile_name=record[18],
                portfolio_photo=json.loads(record[19]) if record[19] else None
            ) for record in records]
        finally:
            await conn.close()

    async def delete(self) -> None:
        # Локальный импорт для избежания циклических зависимостей
        from app.untils import help_defs

        # Удаляем все файлы портфолио перед удалением из БД
        if self.portfolio_photo:
            for photo_path in self.portfolio_photo.values():
                help_defs.delete_file(photo_path)
                logger.info(f"Файл портфолио удален при удалении исполнителя: {photo_path}")

        # Удаляем фото профиля если есть
        if self.profile_photo:
            help_defs.delete_file(self.profile_photo)
            logger.info(f"Фото профиля удалено при удалении исполнителя: {self.profile_photo}")

        # Удаляем из базы данных
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            if self.id:
                cursor = await conn.execute('DELETE FROM workers WHERE id = ?', [self.id])
            else:
                cursor = await conn.execute('DELETE FROM workers WHERE tg_id = ?', [self.tg_id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update_portfolio_photo(self, portfolio_photo: dict) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            portfolio_photo_json = json.dumps(portfolio_photo)
            query = 'UPDATE workers SET portfolio_photo = ? WHERE id = ?'
            params = (portfolio_photo_json, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update_order_counter(self, order_count: int) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE workers SET order_count = ? WHERE id = ?'
            params = (order_count, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update_profile_photo(self, profile_photo: str | None) -> None:
        # Локальный импорт для избежания циклических зависимостей
        from app.untils import help_defs

        # Удаляем старое фото профиля если оно есть
        if self.profile_photo and self.profile_photo != profile_photo:
            help_defs.delete_file(self.profile_photo)
            logger.info(f"Старое фото профиля удалено: {self.profile_photo}")

        # Обновляем в базе данных
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE workers SET profile_photo = ? WHERE id = ?'
            params = (profile_photo, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update_profile_name(self, profile_name: str) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE workers SET profile_name = ? WHERE id = ?'
            params = (profile_name, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
            self.profile_name = profile_name
        finally:
            await conn.close()
    
    async def update_name_violations_count(self, count: int) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE workers SET name_violations_count = ? WHERE id = ?'
            params = (count, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
            self.name_violations_count = count
        finally:
            await conn.close()

    async def update_active(self, active: bool) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE workers SET active = ? WHERE id = ?'
            params = (active, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update_phone_number(self, phone_number: str) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE workers SET phone_number = ? WHERE id = ?'
            params = (phone_number, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update_city(self, city_id: list) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE workers SET city_id = ? WHERE id = ?'
            city_id = [str(x) for x in city_id]
            params = (' | '.join(city_id), self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update_stars(self, stars: int, count_ratings: int) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE workers SET stars = ?, count_ratings = ? WHERE id = ?'
            params = (stars, count_ratings, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def count(cls) -> int:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT COUNT(1) FROM workers')
            record = await cursor.fetchone()
            await cursor.close()
            return int(record[0]) if record else 0
        finally:
            await conn.close()

    async def update_confirmed(self, confirmed: bool) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE workers SET confirmed = ? WHERE id = ?'
            params = (confirmed, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update_individual_entrepreneur(self, individual_entrepreneur: bool) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE workers SET individual_entrepreneur = ? WHERE id = ?'
            params = (individual_entrepreneur, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update_order_count(self, order_count: int) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE workers SET order_count = ? WHERE id = ?'
            params = (order_count, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update_order_count_on_week(self, order_count_on_week: int) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'UPDATE workers SET order_count_on_week = ? WHERE id = ?'
            params = (order_count_on_week, self.id)
            cursor = await conn.execute(query, params)
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update_purchased_contacts(self, purchased_contacts: int = None,
                                        unlimited_contacts_until: str = None) -> None:
        """Обновляет количество купленных контактов или безлимитный период"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            updates = []
            params = []

            if purchased_contacts is not None:
                updates.append('purchased_contacts = ?')
                params.append(purchased_contacts)

            if unlimited_contacts_until is not None:
                updates.append('unlimited_contacts_until = ?')
                params.append(unlimited_contacts_until)

            if updates:
                params.append(self.id)
                query = f"UPDATE workers SET {', '.join(updates)} WHERE id = ?"
                cursor = await conn.execute(query, params)
                await conn.commit()
                await cursor.close()

                # Обновляем локальные значения
                if purchased_contacts is not None:
                    self.purchased_contacts = purchased_contacts
                if unlimited_contacts_until is not None:
                    self.unlimited_contacts_until = unlimited_contacts_until
        finally:
            await conn.close()

    async def update_activity_level(self, new_level: int) -> None:
        """Обновляет уровень активности исполнителя"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'UPDATE workers SET activity_level = ? WHERE id = ?',
                (new_level, self.id)
            )
            await conn.commit()
            await cursor.close()
            self.activity_level = new_level
        finally:
            await conn.close()

    async def change_activity_level(self, change: int) -> int:
        """Изменяет уровень активности на указанное значение и возвращает новый уровень"""
        new_level = max(0, min(100, self.activity_level + change))
        await self.update_activity_level(new_level)
        return new_level

    def get_activity_zone(self) -> tuple[str, str]:
        """Возвращает зону активности и соответствующее сообщение"""
        if self.activity_level >= 74:
            return "🟢", "Все в порядке, доступ полный"
        elif self.activity_level >= 48:
            return "🟡", "Ваша активность снижается, ограничения: можно откликнуться только на 3 заказа в день"
        elif self.activity_level >= 9:
            return "🟠", "Ограничения: можно откликнуться только на 1 заказ в день"
        else:
            return "🔴", "Блокировка откликов: Ваш уровень активности слишком низкий. Чтобы продолжить работу, восстановите активность!"

    def can_make_response(self, responses_today: int) -> bool:
        """Проверяет, может ли исполнитель сделать отклик"""
        if self.activity_level >= 74:  # Зеленая зона
            return True
        elif self.activity_level >= 48:  # Желтая зона
            return responses_today < 3
        elif self.activity_level >= 9:  # Оранжевая зона
            return responses_today < 1
        else:  # Красная зона
            return False

    def get_responses_limit_per_day(self) -> int:
        """Возвращает лимит откликов в день для текущей зоны"""
        if self.activity_level >= 74:  # Зеленая зона
            return -1  # Без ограничений
        elif self.activity_level >= 48:  # Желтая зона
            return 3
        elif self.activity_level >= 9:  # Оранжевая зона
            return 1
        else:  # Красная зона
            return 0


class City:
    def __init__(self, id: int | None, city: str, city_en: str):
        self.id = id
        self.city = city
        self.city_en = city_en

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO cities (city, city_en) VALUES (?, ?)', [self.city, self.city_en])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_city(cls, id: int = None, city_name: str = None, city_en: str = None) -> Optional['City'] | None:
        if id or city_name or city_en:
            conn = await aiosqlite.connect(database='app/data/database/database.db')
            try:
                if id:
                    cursor = await conn.execute('SELECT * FROM cities WHERE id = ?', [id])
                elif city_en:
                    cursor = await conn.execute('SELECT * FROM cities WHERE city_en = ?', [city_en])
                else:
                    cursor = await conn.execute('SELECT * FROM cities WHERE city = ?', [city_name])
                record = await cursor.fetchone()
                await cursor.close()
                if record:
                    return cls(*record)
                return None
            finally:
                await conn.close()

    @classmethod
    async def get_all(cls, sort: bool = True) -> list['City']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            if sort:
                cursor = await conn.execute('SELECT * FROM cities  ORDER BY city')
            else:
                cursor = await conn.execute('SELECT * FROM cities')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(*record) for record in records]
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM cities WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()


class Banned:
    def __init__(self, id: int | None, tg_id: int, ban_counter: int,
                 ban_end, ban_now: bool, forever: bool, ban_reason: str, warning: int = 0):
        self.id = id
        self.tg_id = tg_id
        self.ban_counter = ban_counter
        self.ban_end = datetime.strptime(str(ban_end), '%Y-%m-%d %H:%M:%S.%f') if ban_end else None
        self.ban_now = ban_now
        self.forever = forever
        self.warning = warning
        self.ban_reason = ban_reason

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('INSERT INTO ban_list (tg_id, ban_end, ban_reason) VALUES (?, ?, ?)',
                                        [self.tg_id, self.ban_end, self.ban_reason])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def save_war(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        cursor = await conn.execute('INSERT INTO ban_list (tg_id, warning, ban_now, ban_reason) VALUES (?, ?, ?, ?)',
                                    [self.tg_id, self.warning, False, self.ban_reason])
        await conn.commit()
        await cursor.close()
        await conn.close()

    @classmethod
    async def get_banned(cls, id: int = None, tg_id: int = None) -> Optional['Banned'] | None:
        if id or tg_id:
            conn = await aiosqlite.connect(database='app/data/database/database.db',
                                           detect_types=sqlite3.PARSE_DECLTYPES |
                                                        sqlite3.PARSE_COLNAMES)
            try:
                if id:
                    cursor = await conn.execute('SELECT * FROM ban_list WHERE id = ?', [id])
                else:
                    cursor = await conn.execute('SELECT * FROM ban_list WHERE tg_id = ?', [tg_id])
                record = await cursor.fetchone()
                await cursor.close()
                if record:
                    return cls(
                        id=record[0],
                        tg_id=record[1],
                        ban_counter=record[2],
                        ban_end=record[3],
                        ban_now=True if record[4] == 1 else False,
                        forever=True if record[5] == 1 else False,
                        warning=record[6],
                        ban_reason='не сохранена' if record[7] is None else record[7]
                    )
                return None
            finally:
                await conn.close()

    @classmethod
    async def get_all(cls) -> list['Banned'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT * FROM ban_list')
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [
                    cls(
                        id=record[0],
                        tg_id=record[1],
                        ban_counter=record[2],
                        ban_end=record[3],
                        ban_now=True if record[4] == 1 else False,
                        forever=True if record[5] == 1 else False,
                        warning=record[6],
                        ban_reason='не сохранена' if record[7] is None else record[7]
                    )
                    for record in records
                ]
        finally:
            await conn.close()

    @classmethod
    async def count_active(cls) -> int:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute(
                'SELECT COUNT(1) FROM ban_list WHERE COALESCE(ban_now, 0) = 1 OR COALESCE(forever, 0) = 1')
            record = await cursor.fetchone()
            await cursor.close()
            return int(record[0]) if record else 0
        finally:
            await conn.close()

    @classmethod
    async def get_all_banned_now(cls) -> list['Banned'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT * FROM ban_list WHERE ban_now = ? and forever = ?',
                                        [True, False])
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [
                    cls(
                        id=record[0],
                        tg_id=record[1],
                        ban_counter=record[2],
                        ban_end=record[3],
                        ban_now=True if record[4] == 1 else False,
                        forever=True if record[5] == 1 else False,
                        warning=record[6],
                        ban_reason='не сохранена' if record[7] is None else record[7]
                    )
                    for record in records
                ]
        finally:
            await conn.close()

    async def update(self, ban_counter: int = None, ban_end: str = None, ban_now: bool = None,
                     forever: bool = None, warning: int = None, ban_reason: str = None) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            updates = []
            params = []

            if ban_counter is not None:
                updates.append('ban_counter = ?')
                params.append(ban_counter)

            if ban_end is not None:
                updates.append('ban_end = ?')
                params.append(ban_end)

            if ban_now is not None:
                updates.append('ban_now = ?')
                params.append(ban_now)

            if forever is not None:
                updates.append('forever = ?')
                params.append(forever)

            if warning is not None:
                updates.append('warning = ?')
                params.append(warning)

            if ban_reason is not None:
                updates.append('ban_reason = ?')
                params.append(ban_reason)

            if updates:
                params.append(self.id)
                query = f"UPDATE ban_list SET {', '.join(updates)} WHERE id = ?"
                await conn.execute(query, params)
                await conn.commit()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('DELETE FROM ban_list WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()


class BlockWord:
    def __init__(self, id: int | None, word: str):
        self.id = id
        self.word = word

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO block_list (word) VALUES (?)', [self.word])
            await conn.commit()
            await cursor.close()
            await conn.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM block_list WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['BlockWord']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM block_list')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0], word=record[1]) for record in records]
        finally:
            await conn.close()


class BlockWordMessage:
    def __init__(self, id: int | None, word: str):
        self.id = id
        self.word = word

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO block_list_message (word) VALUES (?)', [self.word])
            await conn.commit()
            await cursor.close()
            await conn.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM block_list_message WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['BlockWordMessage']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM block_list_message')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0], word=record[1]) for record in records]
        finally:
            await conn.close()


class BlockWordPersonal:
    def __init__(self, id: int | None, word: str):
        self.id = id
        self.word = word

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO block_list_personal (word) VALUES (?)', [self.word])
            await conn.commit()
            await cursor.close()
            await conn.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM block_list_personal WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['BlockWordPersonal']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM block_list_personal')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0], word=record[1]) for record in records]
        finally:
            await conn.close()


class BlockWordPhoto:
    def __init__(self, id: int | None, word: str):
        self.id = id
        self.word = word

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO block_list_photo (word) VALUES (?)', [self.word])
            await conn.commit()
            await cursor.close()
            await conn.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM block_list_photo WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['BlockWordPhoto']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM block_list_photo')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0], word=record[1]) for record in records]
        finally:
            await conn.close()


class BlockWordShort:
    def __init__(self, id: int | None, word: str):
        self.id = id
        self.word = word

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO block_list_short (word) VALUES (?)', [self.word])
            await conn.commit()
            await cursor.close()
            await conn.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM block_list_short WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['BlockWordShort']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM block_list_short')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0], word=record[1]) for record in records]
        finally:
            await conn.close()


class BlockWordShortMessage:
    def __init__(self, id: int | None, word: str):
        self.id = id
        self.word = word

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO block_list_short_message (word) VALUES (?)', [self.word])
            await conn.commit()
            await cursor.close()
            await conn.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM block_list_short_message WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['BlockWordShortMessage']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM block_list_short_message')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0], word=record[1]) for record in records]
        finally:
            await conn.close()


class BlockWordShortPersonal:
    def __init__(self, id: int | None, word: str):
        self.id = id
        self.word = word

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO block_list_short_personal (word) VALUES (?)', [self.word])
            await conn.commit()
            await cursor.close()
            await conn.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM block_list_short_personal WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['BlockWordShortPersonal']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM block_list_short_personal')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0], word=record[1]) for record in records]
        finally:
            await conn.close()


class BlockWordShortPhoto:
    def __init__(self, id: int | None, word: str):
        self.id = id
        self.word = word

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO block_list_short_photo (word) VALUES (?)', [self.word])
            await conn.commit()
            await cursor.close()
            await conn.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM block_list_short_photo WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['BlockWordShortPhoto']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM block_list_short_photo')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0], word=record[1]) for record in records]
        finally:
            await conn.close()


class ProfanityWord:
    def __init__(self, id: int | None, word: str):
        self.id = id
        self.word = word

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO profanity_word (word) VALUES (?)', [self.word])
            await conn.commit()
            await cursor.close()
            await conn.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM profanity_word WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['ProfanityWord']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM profanity_word')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0], word=record[1]) for record in records]
        finally:
            await conn.close()


class WhiteWord:
    def __init__(self, id: int | None, word: str):
        self.id = id
        self.word = word

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO white_list (word) VALUES (?)', [self.word])
            await conn.commit()
            await cursor.close()
            await conn.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM white_list WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['WhiteWord']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM white_list')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0], word=record[1]) for record in records]
        finally:
            await conn.close()




class WorkType:
    def __init__(self, id: int | None, work_type: str, template: str | None, template_photo: str | None):
        self.id = id
        self.work_type = work_type
        self.template = template
        self.template_photo = template_photo

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO work_types (work_type) VALUES (?)', [self.work_type])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM work_types WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_work_type(cls, id: int = None, work_type: str = None) -> Optional['WorkType'] | None:
        if id or work_type:
            conn = await aiosqlite.connect(database='app/data/database/database.db')
            try:
                cursor = await conn.execute('SELECT * FROM work_types WHERE id = ?', [id])
                record = await cursor.fetchone()
                await cursor.close()
                if record:
                    return cls(id=record[0], work_type=record[1], template=record[2], template_photo=record[3])
                return None
            finally:
                await conn.close()
        else:
            return None

    @classmethod
    async def get_all(cls) -> list['WorkType']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM work_types')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0], work_type=record[1], template=record[2], template_photo=record[3]) for record in
                    records]
        finally:
            await conn.close()




class WorkerAndRefsAssociation:
    def __init__(self, id: int | None, worker_id: int, ref_id: int,
                 work_condition: bool, ref_condition: bool, worker_bonus: bool = False, ref_bonus: bool = False):
        self.id = id
        self.worker_id = worker_id
        self.ref_id = ref_id
        self.work_condition = work_condition
        self.ref_condition = ref_condition
        self.worker_bonus = worker_bonus
        self.ref_bonus = ref_bonus

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'INSERT INTO worker_and_refs_association (worker_id, ref_id, work_condition) VALUES (?, ?, ?)',
                [self.worker_id, self.ref_id, self.work_condition])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update(self, work_condition: bool = None, ref_condition: bool = None, worker_bonus: bool = None,
                     ref_bonus: bool = None) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            updates = []
            params = []
            if work_condition is not None:
                updates.append('work_condition = ?')
                params.append(work_condition)
            if ref_condition is not None:
                updates.append('ref_condition = ?')
                params.append(ref_condition)
            if worker_bonus is not None:
                updates.append('worker_bonus = ?')
                params.append(worker_bonus)
            if ref_bonus is not None:
                updates.append('ref_bonus = ?')
                params.append(ref_bonus)
            if updates:
                params.append(self.id)
                query = f"UPDATE worker_and_refs_association SET {', '.join(updates)} WHERE id = ?"
                await conn.execute(query, params)
                await conn.commit()
        finally:
            await conn.close()

    @classmethod
    async def get_refs_by_worker(cls, worker_id) -> Optional['WorkerAndRefsAssociation'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM worker_and_refs_association WHERE worker_id = ?', [worker_id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(id=record[0], worker_id=record[1], ref_id=record[2],
                           work_condition=True if record[3] == 1 else False,
                           ref_condition=True if record[4] == 1 else False,
                           worker_bonus=True if record[5] == 1 else False,
                           ref_bonus=True if record[6] == 1 else False
                           )
            return None
        finally:
            await conn.close()

    @classmethod
    async def get_by_ref(cls, ref_id) -> Optional['WorkerAndRefsAssociation'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM worker_and_refs_association WHERE ref_id = ?', [ref_id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(id=record[0], worker_id=record[1], ref_id=record[2],
                           work_condition=True if record[3] == 1 else False,
                           ref_condition=True if record[4] == 1 else False,
                           worker_bonus=True if record[5] == 1 else False,
                           ref_bonus=True if record[6] == 1 else False
                           )
            else:
                return None
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['WorkerAndRefsAssociation'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM worker_and_refs_association')
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(id=record[0],
                            worker_id=record[1],
                            ref_id=record[2],
                            work_condition=True if record[3] == 1 else False,
                            ref_condition=True if record[4] == 1 else False,
                            worker_bonus=True if record[5] == 1 else False,
                            ref_bonus=True if record[6] == 1 else False)
                        for record in records]
            else:
                return None
        finally:
            await conn.close()


class Admin:
    def __init__(self, id: int | None, tg_id: int, tg_name: str, deleted_abs: int, done_abs: int, order_price: int):
        self.id = id
        self.tg_id = tg_id
        self.tg_name = tg_name
        self.deleted_abs = deleted_abs
        self.done_abs = done_abs
        self.order_price = order_price

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'INSERT INTO admins (tg_id, tg_name) VALUES (?, ?)',
                [self.tg_id, self.tg_name])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM admins WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['Admin']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM admins')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0],
                        tg_id=record[1],
                        tg_name=record[2],
                        deleted_abs=record[3],
                        done_abs=record[4],
                        order_price=record[5])
                    for record in records]
        finally:
            await conn.close()

    @classmethod
    async def get_by_tg_id(cls, tg_id: int) -> Optional['Admin'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM admins WHERE tg_id = ?', [tg_id])
            record = await cursor.fetchall()
            await cursor.close()
            if record:
                return cls(id=record[0][0],
                           tg_id=record[0][1],
                           tg_name=record[0][2],
                           deleted_abs=record[0][3],
                           done_abs=record[0][4],
                           order_price=record[0][5])
            else:
                return None

        finally:
            await conn.close()

    async def update(self, deleted_abs: int = None, done_abs: int = None, order_price: int = None) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            updates = []
            params = []

            if deleted_abs is not None:
                updates.append('deleted_abs = ?')
                params.append(deleted_abs)

            if done_abs is not None:
                updates.append('done_abs = ?')
                params.append(done_abs)

            if order_price is not None:
                updates.append('order_price = ?')
                params.append(order_price)

            if updates:
                params.append(self.id)
                query = f"UPDATE admins SET {', '.join(updates)} WHERE id = ?"
                await conn.execute(query, params)
                await conn.commit()
        finally:
            await conn.close()

    @staticmethod
    async def count_distinct_users() -> int:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            query = 'SELECT COUNT(DISTINCT tg_id) FROM (SELECT tg_id FROM customers UNION ALL SELECT tg_id FROM workers) AS all_users'
            cursor = await conn.execute(query)
            record = await cursor.fetchone()
            await cursor.close()
            return int(record[0]) if record else 0
        finally:
            await conn.close()


class Abs:
    def __init__(self, id: int | None, customer_id: int,
                 work_type_id: int, city_id: int, photo_path: dict | None, text_path: str, date_to_delite,
                 count_photo: int, relevance: bool = True, views: int = 0):
        self.id = id
        self.customer_id = customer_id
        self.work_type_id = work_type_id
        self.city_id = city_id
        self.photo_path = photo_path
        self.text_path = text_path
        self.date_to_delite = datetime.strptime(str(date_to_delite), '%Y-%m-%d %H:%M:%S.%f')
        self.relevance = relevance
        self.views = views
        self.count_photo = count_photo

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS abs
                               (
                                   id               INTEGER PRIMARY KEY AUTOINCREMENT,
                                   customer_id      INTEGER NOT NULL,
                                   work_type_id     INTEGER NOT NULL,
                                   city_id          INTEGER NOT NULL,
                                   photo_path       TEXT,
                                   text_path        TEXT    NOT NULL,
                                   date_to_delite   TEXT    NOT NULL,
                                   relevance        INTEGER DEFAULT 1,
                                   views            INTEGER DEFAULT 0,
                                   count_photo      INTEGER DEFAULT 0
                               )
                               ''')
            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            photo_path_json = json.dumps(self.photo_path)
            cursor = await conn.execute(
                'INSERT INTO abs (customer_id, work_type_id, city_id, photo_path, text_path, date_to_delite, count_photo) VALUES (?, ?, ?, ?, ?, ?, ?)',
                [self.customer_id, self.work_type_id, self.city_id, photo_path_json, self.text_path,
                 self.date_to_delite, self.count_photo])
            # Сохраняем ID после вставки
            self.id = cursor.lastrowid
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def delete(self, delite_photo: bool) -> None:
        # Локальный импорт для избежания циклических зависимостей
        from app.untils import help_defs

        if delite_photo:
            if isinstance(self.photo_path, dict):
                for _, item in self.photo_path.items():
                    help_defs.delete_file(item)
            else:
                help_defs.delete_file(self.photo_path)
        help_defs.delete_file(self.text_path)
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('DELETE FROM abs WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update(self, relevance: bool = None, views: int = None, date_to_delite=None, photo_path=None) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            updates = []
            params = []

            if relevance is not None:
                updates.append('relevance = ?')
                params.append(relevance)

            if views is not None:
                updates.append('views = ?')
                self.views += views
                params.append(self.views)

            if date_to_delite is not None:
                updates.append('date_to_delite = ?')
                # Если передан datetime объект, используем его напрямую
                if isinstance(date_to_delite, datetime):
                    self.date_to_delite = date_to_delite
                else:
                    # Если передан timedelta или строка, добавляем к существующей дате
                    if isinstance(date_to_delite, str):
                        self.date_to_delite += datetime.strptime(str(date_to_delite), '%Y-%m-%d %H:%M:%S.%f')
                    else:
                        # Для timedelta объектов
                        self.date_to_delite += date_to_delite
                params.append(self.date_to_delite)

            if photo_path is not None:
                updates.append('photo_path = ?')
                self.photo_path = photo_path
                photo_path_json = json.dumps(photo_path)
                params.append(photo_path_json)

            if updates:
                params.append(self.id)
                query = f"UPDATE abs SET {', '.join(updates)} WHERE id = ?"
                await conn.execute(query, params)
                await conn.commit()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['Abs']:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT * FROM abs')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0],
                        customer_id=record[1],
                        work_type_id=record[2],
                        city_id=record[3],
                        photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if
                        record[4] == 'null' else {'0': record[4]},
                        text_path=record[5],
                        date_to_delite=record[6],
                        relevance=True if record[7] == 1 else False,
                        views=record[8],
                        count_photo=record[9]
                        )
                    for record in records]
        finally:
            await conn.close()

    @classmethod
    async def count(cls) -> int:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT COUNT(1) FROM abs')
            record = await cursor.fetchone()
            await cursor.close()
            return int(record[0]) if record else 0
        finally:
            await conn.close()

    @classmethod
    async def get_all_in_city(cls, city_id: int) -> list['Abs'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT * FROM abs WHERE city_id = ?', [city_id])
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(id=record[0],
                            customer_id=record[1],
                            work_type_id=record[2],
                            city_id=record[3],
                            photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if
                            record[4] == 'null' else {'0': record[4]},
                            text_path=record[5],
                            date_to_delite=record[6],
                            relevance=True if record[7] == 1 else False,
                            views=record[8],
                            count_photo=record[9]
                            ) for record in records]
            else:
                return None
        finally:
            await conn.close()

    @classmethod
    async def get_all_by_customer(cls, customer_id: int) -> list['Abs'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT * FROM abs WHERE customer_id = ?', [customer_id])
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(id=record[0],
                            customer_id=record[1],
                            work_type_id=record[2],
                            city_id=record[3],
                            photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if
                            record[4] == 'null' else {'0': record[4]},
                            text_path=record[5],
                            date_to_delite=record[6],
                            relevance=True if record[7] == 1 else False,
                            views=record[8],
                            count_photo=record[9]
                            ) for record in records]
            else:
                return None
        finally:
            await conn.close()

    @classmethod
    async def get_one(cls, id: int) -> Optional['Abs'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT * FROM abs WHERE id = ?', [id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(id=record[0],
                           customer_id=record[1],
                           work_type_id=record[2],
                           city_id=record[3],
                           photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if
                           record[4] == 'null' else {'0': record[4]},
                           text_path=record[5],
                           date_to_delite=record[6],
                           relevance=True if record[7] == 1 else False,
                           views=record[8],
                           count_photo=record[9]
                           )
            else:
                return None
        finally:
            await conn.close()


class WorkerAndSubscription:
    def __init__(self, worker_id: int, id: int = None, work_type_ids: list = None):
        self.id = id
        self.worker_id = worker_id
        self.work_type_ids = work_type_ids

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            work_type_ids_str = '|'.join(map(str, self.work_type_ids)) if self.work_type_ids else None
            cursor = await conn.execute(
                'INSERT INTO worker_and_subscription (worker_id, work_type_ids) VALUES (?, ?)',
                [self.worker_id, work_type_ids_str])
            await conn.commit()
            self.id = cursor.lastrowid
            await cursor.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM worker_and_subscription WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update(self, work_type_ids: list = None) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            updates = []
            params = []

            if work_type_ids is not None:
                updates.append('work_type_ids = ?')
                work_type_ids_str = '|'.join(map(str, work_type_ids)) if work_type_ids else None
                params.append(work_type_ids_str)

            if updates:
                params.append(self.id)
                query = f"UPDATE worker_and_subscription SET {', '.join(updates)} WHERE id = ?"
                await conn.execute(query, params)
                await conn.commit()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['WorkerAndSubscription']:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT * FROM worker_and_subscription')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0],
                        worker_id=record[1],
                        work_type_ids=record[2].split('|') if record[2] else None)
                    for record in records]
        finally:
            await conn.close()

    @classmethod
    async def get_by_worker(cls, worker_id: int) -> Optional['WorkerAndSubscription']:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT * FROM worker_and_subscription WHERE worker_id = ?', [worker_id])
            records = await cursor.fetchall()
            await cursor.close()
            
            if not records:
                return None
            
            # Если есть несколько записей, берем самую новую (с наибольшим id)
            # и удаляем дублирующие записи
            if len(records) > 1:
                # Сортируем по id (самая новая запись будет последней)
                records.sort(key=lambda x: x[0])
                latest_record = records[-1]
                
                # Удаляем старые дублирующие записи
                old_ids = [record[0] for record in records[:-1]]
                if old_ids:
                    placeholders = ','.join(['?' for _ in old_ids])
                    await conn.execute(f'DELETE FROM worker_and_subscription WHERE id IN ({placeholders})', old_ids)
                    await conn.commit()
                    print(f"[CLEANUP] Removed {len(old_ids)} duplicate worker_and_subscription records for worker {worker_id}")
            else:
                latest_record = records[0]
            
            return cls(id=latest_record[0],
                       worker_id=latest_record[1],
                       work_type_ids=latest_record[2].split('|') if latest_record[2] else None)
        finally:
            await conn.close()

    @classmethod
    async def get_by_id(cls, id: int) -> Optional['WorkerAndSubscription']:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT * FROM worker_and_subscription WHERE id = ?', [id])
            record = await cursor.fetchall()
            await cursor.close()
            return cls(id=record[0][0],
                       worker_id=record[0][1],
                       work_type_ids=record[0][2].split('|') if record[0][2] else None)
        finally:
            await conn.close()


class WorkersAndAbs:
    def __init__(self, worker_id: int, abs_id: int, id: int = None, applyed: bool = None, send_by_worker: int = None,
                 send_by_customer: int = None, customer_messages: str = None, worker_messages: str = None,
                 turn: bool = True, message_timestamps: str = None, last_read_by_worker: int = None, last_read_by_customer: int = None,
                 last_message_by_worker: int = None, last_message_by_customer: int = None):
        self.id = id
        self.worker_id = worker_id
        self.abs_id = abs_id
        self.send_by_worker = send_by_worker
        self.send_by_customer = send_by_customer
        self.applyed = applyed
        self.last_read_by_worker = last_read_by_worker if last_read_by_worker is not None else 0
        self.last_read_by_customer = last_read_by_customer if last_read_by_customer is not None else 0
        self.last_message_by_worker = last_message_by_worker if last_message_by_worker is not None else 0
        self.last_message_by_customer = last_message_by_customer if last_message_by_customer is not None else 0
        step = 0
        if worker_messages:
            # Вычисляем step на основе длины строки
            if len(worker_messages) > 1024:
                step = int(((len(worker_messages) - 1024) / 20))
            elif customer_messages:
                if len(customer_messages) > 1024:
                    step = int(((len(customer_messages) - 1024) / 20))
            
            # Разбиваем строку на список сообщений
            messages_list = worker_messages.split(' | ')
            
            # Если step слишком большой (больше длины списка), берем все сообщения
            if step >= len(messages_list):
                step = 0
            
            self.worker_messages = messages_list[step::]
        else:
            self.worker_messages = ['Исполнитель не отправил сообщение']

        if customer_messages is None:
            if applyed:
                self.customer_messages = []
            else:
                self.customer_messages = []
        else:
            # Разбиваем строку на список сообщений
            customer_messages_list = customer_messages.split(' | ')
            
            # Если step слишком большой (больше длины списка), берем все сообщения
            if step >= len(customer_messages_list):
                step = 0
            
            self.customer_messages = customer_messages_list[step::]
        self.turn = turn
        
        # Парсим временные метки сообщений
        if message_timestamps:
            try:
                self.message_timestamps = json.loads(message_timestamps)
            except (json.JSONDecodeError, TypeError):
                self.message_timestamps = []
        else:
            self.message_timestamps = []

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS workers_and_abs
                               (
                                   id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                                   worker_id                 INTEGER NOT NULL,
                                   abs_id                    INTEGER NOT NULL,
                                   send_by_worker            INTEGER DEFAULT 0,
                                   send_by_customer          INTEGER DEFAULT 0,
                                   applyed                   INTEGER DEFAULT 0,
                                   worker_messages           TEXT,
                                   customer_messages         TEXT,
                                   turn                      INTEGER DEFAULT 1,
                                   message_timestamps        TEXT,
                                   last_read_by_worker       INTEGER DEFAULT 0,
                                   last_read_by_customer     INTEGER DEFAULT 0,
                                   last_message_by_worker    INTEGER DEFAULT 0,
                                   last_message_by_customer  INTEGER DEFAULT 0
                               )
                               ''')
            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'INSERT INTO workers_and_abs (worker_id, abs_id) VALUES (?, ?)',
                [self.worker_id, self.abs_id])
            self.id = cursor.lastrowid  # Сохраняем ID созданной записи
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM workers_and_abs WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update(self, worker_id: int = None, abs_id: int = None,
                     applyed: bool = None, send_by_worker: int = None,
                     send_by_customer: int = None, worker_messages: list = None,
                     customer_messages: list = None, turn: bool = None, 
                     message_timestamps: list = None, last_read_by_worker: int = None,
                     last_read_by_customer: int = None, last_message_by_worker: int = None,
                     last_message_by_customer: int = None) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            updates = []
            params = []

            if worker_id is not None:
                updates.append('worker_id = ?')
                params.append(worker_id)

            if abs_id is not None:
                updates.append('abs_id = ?')
                params.append(abs_id)

            if applyed is not None:
                updates.append('applyed = ?')
                params.append(applyed)

            if send_by_worker is not None:
                updates.append('send_by_worker = ?')
                params.append(send_by_worker)

            if send_by_customer is not None:
                updates.append('send_by_customer = ?')
                params.append(send_by_customer)

            if worker_messages is not None:
                worker_messages_list = ' | '.join(worker_messages)
                updates.append('worker_messages = ?')
                params.append(worker_messages_list)

            if customer_messages is not None:
                customer_messages_list = ' | '.join(customer_messages)
                updates.append('customer_messages = ?')
                params.append(customer_messages_list)

            if turn is not None:
                updates.append('turn = ?')
                params.append(turn)
            
            if message_timestamps is not None:
                timestamps_json = json.dumps(message_timestamps)
                updates.append('message_timestamps = ?')
                params.append(timestamps_json)
            
            if last_read_by_worker is not None:
                updates.append('last_read_by_worker = ?')
                params.append(last_read_by_worker)
            
            if last_read_by_customer is not None:
                updates.append('last_read_by_customer = ?')
                params.append(last_read_by_customer)
            
            if last_message_by_worker is not None:
                updates.append('last_message_by_worker = ?')
                params.append(last_message_by_worker)
            
            if last_message_by_customer is not None:
                updates.append('last_message_by_customer = ?')
                params.append(last_message_by_customer)

            if updates:
                params.append(self.id)
                query = f"UPDATE workers_and_abs SET {', '.join(updates)} WHERE id = ?"
                await conn.execute(query, params)
                await conn.commit()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['WorkersAndAbs']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM workers_and_abs')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0],
                        worker_id=record[1],
                        abs_id=record[2],
                        send_by_worker=True if record[3] == 1 else False,
                        send_by_customer=True if record[4] == 1 else False,
                        applyed=True if record[5] == 1 else False,
                        worker_messages=record[6],
                        customer_messages=record[7],
                        turn=True if record[8] == 1 else False,
                        message_timestamps=record[9] if len(record) > 9 else None,
                        last_read_by_worker=record[10] if len(record) > 10 else 0,
                        last_read_by_customer=record[11] if len(record) > 11 else 0,
                        last_message_by_worker=record[12] if len(record) > 12 else 0,
                        last_message_by_customer=record[13] if len(record) > 13 else 0)
                    for record in records]
        finally:
            await conn.close()

    @classmethod
    async def get_by_worker(cls, worker_id: int) -> list['WorkersAndAbs']:
        """Получить все отклики исполнителя"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM workers_and_abs WHERE worker_id = ?', [worker_id])
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0],
                        worker_id=record[1],
                        abs_id=record[2],
                        send_by_worker=record[3],
                        send_by_customer=record[4],
                        applyed=True if record[5] == 1 else False,
                        worker_messages=record[6],
                        customer_messages=record[7],
                        turn=True if record[8] == 1 else False,
                        message_timestamps=record[9] if len(record) > 9 else None,
                        last_read_by_worker=record[10] if len(record) > 10 else 0,
                        last_read_by_customer=record[11] if len(record) > 11 else 0,
                        last_message_by_worker=record[12] if len(record) > 12 else 0,
                        last_message_by_customer=record[13] if len(record) > 13 else 0)
                    for record in records]
        finally:
            await conn.close()

    @classmethod
    async def get_by_abs(cls, abs_id: int) -> list['WorkersAndAbs']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM workers_and_abs WHERE abs_id = ? ', [abs_id])
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0],
                        worker_id=record[1],
                        abs_id=record[2],
                        send_by_worker=record[3],
                        send_by_customer=record[4],
                        applyed=True if record[5] == 1 else False,
                        worker_messages=record[6],
                        customer_messages=record[7],
                        turn=True if record[8] == 1 else False,
                        message_timestamps=record[9] if len(record) > 9 else None,
                        last_read_by_worker=record[10] if len(record) > 10 else 0,
                        last_read_by_customer=record[11] if len(record) > 11 else 0,
                        last_message_by_worker=record[12] if len(record) > 12 else 0,
                        last_message_by_customer=record[13] if len(record) > 13 else 0
                        )
                    for record in records]
        finally:
            await conn.close()

    @classmethod
    async def get_by_worker_and_abs(cls, worker_id: int, abs_id: int) -> Optional['WorkersAndAbs']:
        """Получить отклик конкретного исполнителя на конкретное объявление"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'SELECT * FROM workers_and_abs WHERE worker_id = ? AND abs_id = ?',
                [worker_id, abs_id]
            )
            record = await cursor.fetchone()
            await cursor.close()

            if record:
                return cls(
                    id=record[0],
                    worker_id=record[1],
                    abs_id=record[2],
                    send_by_worker=record[3],
                    send_by_customer=record[4],
                    applyed=True if record[5] == 1 else False,
                    worker_messages=record[6],
                    customer_messages=record[7],
                    turn=True if record[8] == 1 else False,
                    message_timestamps=record[9] if len(record) > 9 else None,
                    last_read_by_worker=record[10] if len(record) > 10 else 0,
                    last_read_by_customer=record[11] if len(record) > 11 else 0,
                    last_message_by_worker=record[12] if len(record) > 12 else 0,
                    last_message_by_customer=record[13] if len(record) > 13 else 0
                )
            return None
        finally:
            await conn.close()


class BannedAbs:
    def __init__(self, id: int | None, customer_id: int,
                 work_type_id: int, city_id: int, photo_path: str | None, text_path: str, date_to_delite, photos_len):
        self.id = id
        self.customer_id = customer_id
        self.work_type_id = work_type_id
        self.city_id = city_id
        self.photo_path = photo_path
        self.text_path = text_path
        self.date_to_delite = datetime.strptime(str(date_to_delite), '%Y-%m-%d %H:%M:%S.%f')
        self.photos_len = photos_len

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            photo_path_json = json.dumps(self.photo_path)
            cursor = await conn.execute(
                'INSERT INTO banned_abs (customer_id, work_type_id, work_type_id, photo_path, text_path, date_to_delite, photos_len) VALUES (?, ?, ?, ?, ?, ?, ?)',
                [self.customer_id, self.work_type_id, self.city_id, photo_path_json, self.text_path,
                 self.date_to_delite, self.photos_len])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def delete(self, delite_photo: bool) -> None:
        # Локальный импорт для избежания циклических зависимостей
        from app.untils import help_defs

        if delite_photo:
            if isinstance(self.photo_path, dict):
                for _, item in self.photo_path.items():
                    help_defs.delete_file(item)
            else:
                help_defs.delete_file(self.photo_path)
        help_defs.delete_file(self.text_path)
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('DELETE FROM banned_abs WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['BannedAbs']:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT * FROM banned_abs')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0],
                        customer_id=record[1],
                        work_type_id=record[2],
                        city_id=record[3],
                        photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if
                        record[4] == 'null' else {'0': record[4]},
                        text_path=record[5],
                        date_to_delite=record[6],
                        photos_len=record[7])
                    for record in records]
        finally:
            await conn.close()

    @classmethod
    async def count(cls) -> int:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT COUNT(1) FROM banned_abs')
            record = await cursor.fetchone()
            await cursor.close()
            return int(record[0]) if record else 0
        finally:
            await conn.close()

    @classmethod
    async def get_all_by_customer(cls, customer_id: int) -> list['BannedAbs'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT * FROM banned_abs WHERE customer_id = ?', [customer_id])
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(id=record[0],
                            customer_id=record[1],
                            work_type_id=record[2],
                            city_id=record[3],
                            photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if
                            record[4] == 'null' else {'0': record[4]},
                            text_path=record[5],
                            date_to_delite=record[6],
                            photos_len=record[7]) for record in records]
            else:
                return None
        finally:
            await conn.close()

    @classmethod
    async def get_one(cls, id: int) -> Optional['BannedAbs'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('SELECT * FROM banned_abs WHERE id = ?', [id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(id=record[0],
                           customer_id=record[1],
                           work_type_id=record[2],
                           city_id=record[3],
                           photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if
                           record[4] == 'null' else {'0': record[4]},
                           text_path=record[5],
                           date_to_delite=record[6],
                           photos_len=record[7])
            else:
                return None
        finally:
            await conn.close()


class WorkerAndCustomer:
    def __init__(self, customer_id: int,
                 worker_id: int, id: int = None):
        self.id = id
        self.customer_id = customer_id
        self.worker_id = worker_id

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS worker_and_customer
                               (
                                   id           INTEGER PRIMARY KEY AUTOINCREMENT,
                                   customer_id  INTEGER NOT NULL,
                                   worker_id    INTEGER NOT NULL
                               )
                               ''')
            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute(
                'INSERT INTO worker_and_customer (customer_id, worker_id) VALUES (?, ?)',
                [self.customer_id, self.worker_id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('DELETE FROM worker_and_customer WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_by_worker_and_customer(cls, worker_id: int, customer_id: int) -> Optional['WorkerAndCustomer']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM worker_and_customer WHERE worker_id = ? and customer_id = ?',
                                        [worker_id, customer_id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(id=record[0],
                           customer_id=record[1],
                           worker_id=record[2])
        finally:
            await conn.close()


class UserAndSupportQueue:
    def __init__(self, id: int | None, user_tg_id: int, user_messages: str, admin_messages: str = None,
                 turn: bool = True):
        self.id = id
        self.user_tg_id = user_tg_id
        self.user_messages = user_messages

        step = 0
        if user_messages:
            if len(user_messages) > 512:
                step = int(((len(user_messages) - 512) / 20))
            elif admin_messages:
                if len(admin_messages) > 512:
                    step = int(((len(admin_messages) - 512) / 20))
            self.user_messages = (user_messages.split(' | '))[step::]
        else:
            self.user_messages = []

        if admin_messages is None:
            self.admin_messages = []
        else:
            self.admin_messages = (admin_messages.split(' | '))[step::]
        self.turn = turn

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS user_and_support_queue
                               (
                                   id              INTEGER PRIMARY KEY AUTOINCREMENT,
                                   user_tg_id      INTEGER NOT NULL,
                                   user_messages   TEXT,
                                   admin_messages  TEXT,
                                   turn            INTEGER DEFAULT 1
                               )
                               ''')
            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO user_and_support_queue (user_tg_id, user_messages) VALUES (?, ?)',
                                        [self.user_tg_id, ' | '.join(self.user_messages)])
            await conn.commit()
            await cursor.close()
            await conn.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM user_and_support_queue WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update(self, user_messages: list = None,
                     admin_messages: list = None, turn: bool = None) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            updates = []
            params = []

            if user_messages is not None:
                worker_messages_list = ' | '.join(user_messages)
                updates.append('user_messages = ?')
                params.append(worker_messages_list)

            if admin_messages is not None:
                customer_messages_list = ' | '.join(admin_messages)
                updates.append('admin_messages = ?')
                params.append(customer_messages_list)

            if turn is not None:
                updates.append('turn = ?')
                params.append(turn)

            if updates:
                params.append(self.id)
                query = f"UPDATE user_and_support_queue SET {', '.join(updates)} WHERE id = ?"
                await conn.execute(query, params)
                await conn.commit()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['UserAndSupportQueue'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM user_and_support_queue')
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(id=record[0], user_tg_id=record[1], user_messages=record[2], admin_messages=record[3],
                            turn=True if record[4] == 1 else False) for record in records]
            else:
                return None
        finally:
            await conn.close()

    @classmethod
    async def get_one_by_tg_id(cls, user_tg_id: int) -> Optional['UserAndSupportQueue'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM user_and_support_queue WHERE user_tg_id = ?', [user_tg_id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(id=record[0], user_tg_id=record[1], user_messages=record[2], admin_messages=record[3],
                           turn=True if record[4] == 1 else False)
            else:
                return None
        finally:
            await conn.close()

    @classmethod
    async def get_one_by_id(cls, id: int) -> Optional['UserAndSupportQueue'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM user_and_support_queue WHERE id = ?', [id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(id=record[0], user_tg_id=record[1], user_messages=record[2], admin_messages=record[3],
                           turn=True if record[4] == 1 else False)
            else:
                return None
        finally:
            await conn.close()


class InfoHaltura:
    def __init__(self, id: int | None, text_path: str):
        self.id = id
        self.text_path = text_path

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO info (text_path) VALUES (?)', [self.text_path])
            await conn.commit()
            await cursor.close()
            await conn.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM info WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['InfoHaltura'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM info')
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(id=record[0], text_path=record[1]) for record in records]
            else:
                return None
        finally:
            await conn.close()

    @classmethod
    async def get_one_by_id(cls, id: int) -> Optional['InfoHaltura'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM info WHERE id', [id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(id=record[0], text_path=record[1])
            else:
                return None
        finally:
            await conn.close()


class WorkerAndReport:
    def __init__(self, worker_id: int, abs_id: int, id: int = None):
        self.id = id
        self.abs_id = abs_id
        self.worker_id = worker_id

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS worker_and_report
                               (
                                   id         INTEGER PRIMARY KEY AUTOINCREMENT,
                                   worker_id  INTEGER NOT NULL,
                                   abs_id     INTEGER NOT NULL
                               )
                               ''')
            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute(
                'INSERT INTO worker_and_report (abs_id, worker_id) VALUES (?, ?)',
                [self.abs_id, self.worker_id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('DELETE FROM worker_and_report WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    # Функция get_by_worker_and_abs удалена - использовалась только для откликов

    @classmethod
    async def get_by_worker(cls, worker_id: int) -> list['WorkerAndReport'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM worker_and_report WHERE worker_id = ?', [worker_id])
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(id=record[0], worker_id=record[1], abs_id=record[2]) for record in records]
            else:
                return None
        finally:
            await conn.close()

    @classmethod
    async def get_by_abs(cls, abs_id: int) -> list['WorkerAndReport'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM worker_and_report WHERE abs_id = ?', [abs_id])
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(id=record[0], worker_id=record[1], abs_id=record[2]) for record in records]
            else:
                return None
        finally:
            await conn.close()


class WorkerAndBadResponse:
    def __init__(self, worker_id: int, abs_id: int, id: int = None):
        self.id = id
        self.abs_id = abs_id
        self.worker_id = worker_id

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute(
                'INSERT INTO worker_and_bad_response (abs_id, worker_id) VALUES (?, ?)',
                [self.abs_id, self.worker_id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute('DELETE FROM worker_and_bad_response WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    # Функция get_by_worker_and_abs удалена - использовалась только для откликов

    @classmethod
    async def get_by_worker(cls, worker_id: int) -> list['WorkerAndBadResponse'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM worker_and_bad_response WHERE worker_id = ?', [worker_id])
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(id=record[0], worker_id=record[1], abs_id=record[2]) for record in records]
            else:
                return None
        finally:
            await conn.close()

    @classmethod
    async def get_by_abs(cls, abs_id: int) -> list['WorkerAndBadResponse'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM worker_and_bad_response WHERE abs_id = ?', [abs_id])
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(id=record[0], worker_id=record[1], abs_id=record[2]) for record in records]
            else:
                return None
        finally:
            await conn.close()


class AskAnswer:
    def __init__(self, questions: list, answer: str, id: int = None):
        self.id = id
        self.questions = questions
        self.answer = answer

    @classmethod
    async def get_all(cls) -> list['AskAnswer'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM ask_answer')
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(id=record[0], questions=record[1].split(' | '), answer=record[2]) for record in records]
            else:
                return None
        finally:
            await conn.close()


# "⣿⣿⣿⡇⢩⠘⣴⣿⣥⣤⢦⢁⠄⠉⡄⡇⠛⠛⠛⢛⣭⣾⣿⣿⡏
# ⣿⣿⣿⡇⠹⢇⡹⣿⣿⣛⣓⣿⡿⠞⠑⣱⠄⢀⣴⣿⣿⣿⣿⡟
# ⣿⣿⣿⣧⣸⡄⣿⣪⡻⣿⠿⠋⠄⠄⣀⣀⢡⣿⣿⣿⣿⡿⠋
# ⠘⣿⣿⣿⣿⣷⣭⣓⡽⡆⡄⢀⣤⣾⣿⣿⣿⣿⣿⡿⠋
# ⠄⢨⡻⡇⣿⢿⣿⣿⣭⡶⣿⣿⣿⣜⢿⡇⡿⠟⠉
# ⠄⠸⣷⡅⣫⣾⣿⣿⣿⣷⣙⢿⣿⣿⣷⣦⣚⡀
# ⠄⠄⢉⣾⡟⠙⠈⢻⣿⣷⣅⢻⣿⣿⣿⣿⣿⣶⣶⡆⠄⡀
# ⠄⢠⣿⣿⣧⣀⣀⣀⣀⣼⣿⣿⣿⡎⢿⣿⣿⣿⣿⣿⣿⣇⠄
# ⠄⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢇⣎⢿⣿⣿⣿⣿⣿⣿⣿⣶⣶
# ⠄⠄⠻⢿⣿⣿⣿⣿⣿⣿⣿⢟⣫⣾⣿⣷⡹⣿⣿⣿⣿⣿⣿⣿⡟
# ⠄⠄⠄⠄⢮⣭⣍⡭⣭⡵⣾⣿⣿⣿⡎⣿⣿⣌⠻⠿⠿⠿⠟⠋
# ⠄⠄⠄⠄⠈⠻⣿⣿⣿⣿⣹⣿⣿⣿⡇⣿⣿⡿
# ⠄⠄⣀⣴⣾⣶⡞⣿⣿⣿⣿⣿⣿⣿⣾⣿⡿⠃
# ⣠⣾⣿⣿⣿⣿⣿⣹⣿⣿⣿⣿⣿⡟⣹⣿⣳⡄"


class ContactTariff:
    """Модель для тарифов покупки контактов"""

    def __init__(self, id: int | None, name: str, contacts_count: int, price: int,
                 unlimited: bool = False, unlimited_days: int = None):
        self.id = id
        self.name = name
        self.contacts_count = contacts_count  # Количество контактов (для безлимита = -1)
        self.price = price  # Цена в копейках
        self.unlimited = unlimited  # Безлимитный тариф
        self.unlimited_days = unlimited_days  # Количество дней для безлимита

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS contact_tariffs
                               (
                                   id              INTEGER PRIMARY KEY AUTOINCREMENT,
                                   name            TEXT    NOT NULL,
                                   contacts_count  INTEGER NOT NULL,
                                   price           INTEGER NOT NULL,
                                   unlimited       INTEGER DEFAULT 0,
                                   unlimited_days  INTEGER
                               )
                               ''')
            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'INSERT INTO contact_tariffs (name, contacts_count, price, unlimited, unlimited_days) VALUES (?, ?, ?, ?, ?)',
                (self.name, self.contacts_count, self.price, self.unlimited, self.unlimited_days))
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['ContactTariff']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM contact_tariffs ORDER BY price ASC')
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [
                    cls(
                        id=record[0],
                        name=record[1],
                        contacts_count=record[2],
                        price=record[3],
                        unlimited=bool(record[4]),
                        unlimited_days=record[5]
                    )
                    for record in records
                ]
            return []
        finally:
            await conn.close()

    @classmethod
    async def get_by_id(cls, id: int) -> Optional['ContactTariff']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM contact_tariffs WHERE id = ?', [id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(
                    id=record[0],
                    name=record[1],
                    contacts_count=record[2],
                    price=record[3],
                    unlimited=bool(record[4]),
                    unlimited_days=record[5]
                )
            return None
        finally:
            await conn.close()


class WorkerRating:
    """Модель для оценок исполнителей заказчиками"""

    def __init__(self, id: int | None, worker_id: int, customer_id: int, abs_id: int,
                 rating: int, comment: str = None, created_at: str = None):
        self.id = id
        self.worker_id = worker_id
        self.customer_id = customer_id
        self.abs_id = abs_id
        self.rating = rating  # Оценка от 1 до 5
        self.comment = comment
        self.created_at = created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS worker_ratings
                               (
                                   id          INTEGER PRIMARY KEY AUTOINCREMENT,
                                   worker_id   INTEGER NOT NULL,
                                   customer_id INTEGER NOT NULL,
                                   abs_id      INTEGER NOT NULL,
                                   rating      INTEGER NOT NULL,
                                   comment     TEXT,
                                   created_at  TEXT    NOT NULL
                               )
                               ''')
            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'INSERT INTO worker_ratings (worker_id, customer_id, abs_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                (self.worker_id, self.customer_id, self.abs_id, self.rating, self.comment, self.created_at))
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_by_worker_and_abs(cls, worker_id: int, abs_id: int) -> Optional['WorkerRating']:
        """Получить оценку конкретного исполнителя за конкретное объявление"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'SELECT * FROM worker_ratings WHERE worker_id = ? AND abs_id = ?',
                [worker_id, abs_id]
            )
            record = await cursor.fetchone()
            await cursor.close()

            if record:
                return cls(
                    id=record[0],
                    worker_id=record[1],
                    customer_id=record[2],
                    abs_id=record[3],
                    rating=record[4],
                    comment=record[5],
                    created_at=record[6]
                )
            return None
        finally:
            await conn.close()

    @classmethod
    async def get_by_worker(cls, worker_id: int) -> list['WorkerRating']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'SELECT * FROM worker_ratings WHERE worker_id = ? ORDER BY created_at DESC',
                [worker_id])
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [
                    cls(
                        id=record[0],
                        worker_id=record[1],
                        customer_id=record[2],
                        abs_id=record[3],
                        rating=record[4],
                        comment=record[5],
                        created_at=record[6]
                    )
                    for record in records
                ]
            return []
        finally:
            await conn.close()


class WorkerCitySubscription:
    """Модель для подписок исполнителей на дополнительные города"""

    def __init__(self, id: int | None, worker_id: int, city_ids: list,
                 subscription_start: str, subscription_end: str,
                 subscription_months: int, price: int, active: bool = True,
                 purchased_city_count: int = None):
        self.id = id
        self.worker_id = worker_id
        self.city_ids = city_ids
        self.subscription_start = subscription_start
        self.subscription_end = subscription_end
        self.subscription_months = subscription_months
        self.price = price
        self.active = active
        # purchased_city_count обязателен
        if purchased_city_count is None:
            raise ValueError("purchased_city_count is required")
        self.purchased_city_count = purchased_city_count

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        """Создает таблицу если она не существует"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            
            # Создаем новую таблицу
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS worker_city_subscriptions
                               (
                                   id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                                   worker_id           INTEGER NOT NULL,
                                   city_ids            TEXT    NOT NULL,
                                   subscription_start  TEXT    NOT NULL,
                                   subscription_end    TEXT    NOT NULL,
                                   subscription_months INTEGER NOT NULL,
                                   price               INTEGER NOT NULL,
                                   active              INTEGER DEFAULT 1,
                                   purchased_city_count INTEGER NOT NULL
                               )
                               ''')
            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        await self.create_table_if_not_exists()  # Создаем таблицу если не существует
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            city_ids_str = '|'.join(map(str, self.city_ids))
            cursor = await conn.execute(
                'INSERT INTO worker_city_subscriptions (worker_id, city_ids, subscription_start, subscription_end, subscription_months, price, active, purchased_city_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                [self.worker_id, city_ids_str, self.subscription_start, self.subscription_end,
                 self.subscription_months, self.price, self.active, self.purchased_city_count])
            await conn.commit()
            self.id = cursor.lastrowid
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_active_by_worker(cls, worker_id: int) -> list['WorkerCitySubscription']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'SELECT * FROM worker_city_subscriptions WHERE worker_id = ? AND active = 1',
                [worker_id])
            records = await cursor.fetchall()
            await cursor.close()

            subscriptions = []
            for record in records:
                city_ids = [int(x) for x in record[2].split('|')] if record[2] else []
                subscriptions.append(cls(
                    id=record[0],
                    worker_id=record[1],
                    city_ids=city_ids,
                    subscription_start=record[3],
                    subscription_end=record[4],
                    subscription_months=record[5],
                    price=record[6],
                    active=bool(record[7]),
                    purchased_city_count=record[8]
                ))
            return subscriptions
        finally:
            await conn.close()

    @classmethod
    async def get_expiring_tomorrow(cls) -> list['WorkerCitySubscription']:
        from datetime import datetime, timedelta
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            cursor = await conn.execute(
                'SELECT * FROM worker_city_subscriptions WHERE subscription_end = ? AND active = 1',
                [tomorrow])
            records = await cursor.fetchall()
            await cursor.close()

            subscriptions = []
            for record in records:
                city_ids = [int(x) for x in record[2].split('|')] if record[2] else []
                subscriptions.append(cls(
                    id=record[0],
                    worker_id=record[1],
                    city_ids=city_ids,
                    subscription_start=record[3],
                    subscription_end=record[4],
                    subscription_months=record[5],
                    price=record[6],
                    active=bool(record[7]),
                    purchased_city_count=record[8]
                ))
            return subscriptions
        finally:
            await conn.close()

    async def deactivate(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'UPDATE worker_city_subscriptions SET active = 0 WHERE id = ?',
                [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()


class ContactExchange:
    """Модель для отслеживания обмена контактами"""

    def __init__(self, id: int | None, worker_id: int, customer_id: int, abs_id: int,
                 contacts_sent: bool = False, contacts_purchased: bool = False,
                 message_id: int = None, created_at: str = None, updated_at: str = None):
        self.id = id
        self.worker_id = worker_id
        self.customer_id = customer_id
        self.abs_id = abs_id
        self.contacts_sent = contacts_sent
        self.contacts_purchased = contacts_purchased
        self.message_id = message_id
        self.created_at = created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.updated_at = updated_at

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS contact_exchanges
                               (
                                   id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                                   worker_id          INTEGER NOT NULL,
                                   customer_id        INTEGER NOT NULL,
                                   abs_id             INTEGER NOT NULL,
                                   contacts_sent      INTEGER DEFAULT 0,
                                   contacts_purchased INTEGER DEFAULT 0,
                                   created_at         TEXT    NOT NULL,
                                   updated_at         TEXT,
                                   message_id         INTEGER
                               )
                               ''')
            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'INSERT INTO contact_exchanges (worker_id, customer_id, abs_id, contacts_sent, contacts_purchased, message_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (self.worker_id, self.customer_id, self.abs_id, self.contacts_sent,
                 self.contacts_purchased, self.message_id, self.created_at, self.updated_at))
            self.id = cursor.lastrowid
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update(self, contacts_sent: bool = None, contacts_purchased: bool = None, message_id: int = None) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            updates = []
            params = []

            if contacts_sent is not None:
                updates.append('contacts_sent = ?')
                params.append(contacts_sent)

            if contacts_purchased is not None:
                updates.append('contacts_purchased = ?')
                params.append(contacts_purchased)

            if message_id is not None:
                updates.append('message_id = ?')
                params.append(message_id)

            if updates:
                updates.append('updated_at = ?')
                params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                params.append(self.id)

                query = f"UPDATE contact_exchanges SET {', '.join(updates)} WHERE id = ?"
                print(query)
                print(params)
                cursor = await conn.execute(query, params)
                await conn.commit()
                await cursor.close()

                # Обновляем локальные значения
                if contacts_sent is not None:
                    self.contacts_sent = contacts_sent
                if contacts_purchased is not None:
                    self.contacts_purchased = contacts_purchased
        finally:
            await conn.close()

    @classmethod
    async def get_by_worker_and_abs(cls, worker_id: int, abs_id: int) -> Optional['ContactExchange']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'SELECT * FROM contact_exchanges WHERE worker_id = ? AND abs_id = ?',
                [worker_id, abs_id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(
                    id=record[0],
                    worker_id=record[1],
                    customer_id=record[2],
                    abs_id=record[3],
                    contacts_sent=bool(record[4]),
                    contacts_purchased=bool(record[5]),
                    created_at=record[6],
                    updated_at=record[7],
                    message_id=record[8],
                )
            return None
        finally:
            await conn.close()

    @classmethod
    async def create_or_update(cls, worker_id: int, customer_id: int, abs_id: int,
                               contacts_sent: bool = False, contacts_purchased: bool = False) -> 'ContactExchange':
        """Создает новую запись или обновляет существующую"""
        existing = await cls.get_by_worker_and_abs(worker_id, abs_id)

        if existing:
            # Проверяем, не пытаемся ли мы сделать повторное действие
            if contacts_sent and existing.contacts_sent:
                raise ValueError("Контакты уже были отправлены")
            if contacts_purchased and existing.contacts_purchased:
                raise ValueError("Контакты уже были куплены")

            await existing.update(contacts_sent=contacts_sent, contacts_purchased=contacts_purchased)
            return existing
        else:
            new_exchange = cls(
                id=None,
                worker_id=worker_id,
                customer_id=customer_id,
                abs_id=abs_id,
                contacts_sent=contacts_sent,
                contacts_purchased=contacts_purchased
            )
            await new_exchange.save()
            return new_exchange

    async def delete(self) -> None:
        """Удаляет запись ContactExchange"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM contact_exchanges WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_by_abs(cls, abs_id: int) -> list['ContactExchange']:
        """Получает все записи ContactExchange для объявления"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'SELECT * FROM contact_exchanges WHERE abs_id = ?',
                [abs_id])
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(
                    id=record[0],
                    worker_id=record[1],
                    customer_id=record[2],
                    abs_id=record[3],
                    contacts_sent=bool(record[4]),
                    contacts_purchased=bool(record[5]),
                    created_at=record[6],
                    updated_at=record[7]
                ) for record in records]
            return []
        finally:
            await conn.close()

    @classmethod
    async def count_by_worker(cls, worker_id: int) -> int:
        """Подсчитывает количество купленных контактов исполнителем"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'SELECT COUNT(*) FROM contact_exchanges WHERE worker_id = ? AND contacts_purchased = 1',
                [worker_id])
            count = await cursor.fetchone()
            await cursor.close()
            return count[0] if count else 0
        finally:
            await conn.close()

    # Функция get_status удалена - использовалась только для откликов


class WorkerRank:
    """Модель для рангов исполнителей"""

    RANK_TYPES = {
        'bronze': {'emoji': '🥉', 'name': 'Бронза', 'orders_required': 0, 'work_types_limit': 1},
        'silver': {'emoji': '🥈', 'name': 'Серебро', 'orders_required': 3, 'work_types_limit': 5},
        'gold': {'emoji': '🥇', 'name': 'Золото', 'orders_required': 5, 'work_types_limit': 10},
        'platinum': {'emoji': '💎', 'name': 'Платина', 'orders_required': 10, 'work_types_limit': None}
    }

    def get_rank_description(self) -> str:
        """Возвращает полное описание ранга"""
        orders = self.orders_this_month
        rank_name = self.get_rank_name()
        rank_emoji = self.get_rank_emoji()

        description = (
            f"**Ваш ранг:** {rank_emoji} {rank_name}\n"
            f"**Выполнено заказов за 30 дней:** {orders}\n\n"
            "**🔹 Уровни рангов**\n\n"
            "🥉 **Бронза** — 0–2 заказа\n"
            "Доступно 1 направление для получения заказов.\n\n"
            "🥈 **Серебро** — 3–4 заказа\n"
            "Можно выбрать до 5 направлений.\n\n"
            "🥇 **Золото** — 5–9 заказов\n"
            "Можно выбрать до 10 направлений, приоритет выше.\n\n"
            "💎 **Платина** — 10+ заказов\n"
            "Доступны все направления без ограничений, максимальный приоритет.\n\n"
            "💡 Чтобы повысить ранг, выполняйте больше заказов в течение 30 дней.\n"
            "Ранг может снизиться, если заказы не выполняются."
        )

        return description

    def __init__(self, id: int | None, worker_id: int, rank_type: str,
                 current_rank: str, completed_orders_count: int,
                 orders_this_month: int, last_updated: str, created_at: str):
        self.id = id
        self.worker_id = worker_id
        self.rank_type = rank_type
        self.current_rank = current_rank
        self.completed_orders_count = completed_orders_count
        self.orders_this_month = orders_this_month
        self.last_updated = last_updated
        self.created_at = created_at

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        """Создает таблицу если она не существует"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS worker_ranks
                               (
                                   id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                                   worker_id              INTEGER NOT NULL,
                                   rank_type              TEXT    NOT NULL,
                                   current_rank           TEXT    NOT NULL,
                                   completed_orders_count INTEGER DEFAULT 0,
                                   orders_this_month      INTEGER DEFAULT 0,
                                   last_updated           TEXT    NOT NULL,
                                   created_at             TEXT    NOT NULL,
                                   FOREIGN KEY (worker_id) REFERENCES workers (id)
                               )
                               ''')

            # Создание индексов
            await conn.execute('''
                               CREATE INDEX IF NOT EXISTS idx_worker_ranks_worker_id
                                   ON worker_ranks (worker_id)
                               ''')

            await conn.execute('''
                               CREATE INDEX IF NOT EXISTS idx_worker_ranks_rank_type
                                   ON worker_ranks (rank_type)
                               ''')

            await conn.execute('''
                               CREATE INDEX IF NOT EXISTS idx_worker_ranks_updated
                                   ON worker_ranks (last_updated)
                               ''')

            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        """Сохраняет ранг в базу данных"""
        await self.create_table_if_not_exists()
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            if self.id is None:
                # Создание нового ранга
                cursor = await conn.execute(
                    'INSERT INTO worker_ranks (worker_id, rank_type, current_rank, completed_orders_count, orders_this_month, last_updated, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    [self.worker_id, self.rank_type, self.current_rank, self.completed_orders_count,
                     self.orders_this_month, self.last_updated, self.created_at])
                self.id = cursor.lastrowid
            else:
                # Обновление существующего ранга
                await conn.execute(
                    'UPDATE worker_ranks SET rank_type = ?, current_rank = ?, completed_orders_count = ?, orders_this_month = ?, last_updated = ? WHERE id = ?',
                    [self.rank_type, self.current_rank, self.completed_orders_count, self.orders_this_month,
                     self.last_updated, self.id])

            await conn.commit()
        finally:
            await conn.close()

    @classmethod
    async def get_by_worker(cls, worker_id: int) -> 'WorkerRank | None':
        """Получает ранг исполнителя"""
        await cls.create_table_if_not_exists()
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'SELECT * FROM worker_ranks WHERE worker_id = ? ORDER BY last_updated DESC LIMIT 1',
                [worker_id])
            record = await cursor.fetchone()
            await cursor.close()

            if record:
                return cls(
                    id=record[0],
                    worker_id=record[1],
                    rank_type=record[2],
                    current_rank=record[3],
                    completed_orders_count=record[4],
                    orders_this_month=record[5],
                    last_updated=record[6],
                    created_at=record[7]
                )
            return None
        finally:
            await conn.close()

    @classmethod
    async def calculate_rank(cls, worker_id: int) -> 'WorkerRank':
        """Рассчитывает ранг исполнителя на основе выполненных заказов за последние 30 дней"""
        from datetime import datetime, timedelta

        # Получаем количество выполненных заказов за последние 30 дней
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            # Вычисляем дату 30 дней назад
            date_30_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

            # Подсчитываем заказы за последние 30 дней (завершенные заказы с оценками)
            cursor = await conn.execute('''
                                        SELECT COUNT(*)
                                        FROM worker_ratings
                                        WHERE worker_id = ?
                                          AND created_at >= ?
                                        ''', [worker_id, date_30_days_ago])

            orders_last_30_days = (await cursor.fetchone())[0]
            await cursor.close()

            # Подсчитываем общее количество выполненных заказов
            cursor = await conn.execute('''
                                        SELECT COUNT(*)
                                        FROM worker_ratings
                                        WHERE worker_id = ?
                                        ''', [worker_id])

            completed_orders_count = (await cursor.fetchone())[0]
            await cursor.close()

        finally:
            await conn.close()

        # Определяем ранг на основе заказов за последние 30 дней
        rank_type = 'bronze'
        if orders_last_30_days >= 10:
            rank_type = 'platinum'
        elif orders_last_30_days >= 5:
            rank_type = 'gold'
        elif orders_last_30_days >= 3:
            rank_type = 'silver'

        rank_info = cls.RANK_TYPES[rank_type]
        current_rank = rank_info['emoji']
        last_updated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        return cls(
            id=None,
            worker_id=worker_id,
            rank_type=rank_type,
            current_rank=current_rank,
            completed_orders_count=completed_orders_count,
            orders_this_month=orders_last_30_days,  # Используем это поле для хранения заказов за 30 дней
            last_updated=last_updated,
            created_at=created_at
        )

    @classmethod
    async def get_or_create_rank(cls, worker_id: int) -> 'WorkerRank':
        """Получает существующий ранг или создает новый"""
        await cls.create_table_if_not_exists()

        # Получаем существующий ранг
        existing_rank = await cls.get_by_worker(worker_id)

        # Рассчитываем текущий ранг
        current_rank = await cls.calculate_rank(worker_id)

        # Если ранг изменился или не существует, обновляем/создаем
        if not existing_rank or existing_rank.rank_type != current_rank.rank_type:
            # Проверяем, изменился ли ранг (не первое создание)
            rank_changed = existing_rank is not None and existing_rank.rank_type != current_rank.rank_type

            # Определяем направление изменения ранга (повышение или понижение)
            old_rank_level = 0
            new_rank_level = 0
            if rank_changed:
                rank_levels = {'bronze': 1, 'silver': 2, 'gold': 3, 'platinum': 4}
                old_rank_level = rank_levels.get(existing_rank.rank_type, 0)
                new_rank_level = rank_levels.get(current_rank.rank_type, 0)

            await current_rank.save()
            
            # Примечание: Счетчик изменений направлений НЕ сбрасывается при изменении ранга
            # Он сбрасывается только через 30 дней после последнего изменения
            # Выбор/добавление направлений НЕ считается изменением (только замена)
            
            return current_rank
        else:
            # Обновляем статистику в существующем ранге
            existing_rank.completed_orders_count = current_rank.completed_orders_count
            existing_rank.orders_this_month = current_rank.orders_this_month
            existing_rank.last_updated = current_rank.last_updated
            await existing_rank.save()
            return existing_rank

    def get_rank_name(self) -> str:
        """Возвращает название ранга"""
        return self.RANK_TYPES.get(self.rank_type, {}).get('name', 'Бронза')

    def get_rank_emoji(self) -> str:
        """Возвращает эмодзи ранга"""
        return self.RANK_TYPES.get(self.rank_type, {}).get('emoji', '🥉')

    def get_work_types_limit(self) -> int | None:
        """Возвращает лимит направлений для ранга"""
        return self.RANK_TYPES.get(self.rank_type, {}).get('work_types_limit', 1)


class WorkerDailyResponses:
    """Модель для отслеживания откликов исполнителей в день"""

    def __init__(self, id: int = None, worker_id: int = None, date: str = None,
                 responses_count: int = 0, created_at: str = None, updated_at: str = None):
        self.id = id
        self.worker_id = worker_id
        self.date = date
        self.responses_count = responses_count
        self.created_at = created_at
        self.updated_at = updated_at

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS worker_daily_responses
                               (
                                   id               INTEGER PRIMARY KEY AUTOINCREMENT,
                                   worker_id        INTEGER NOT NULL,
                                   date             TEXT    NOT NULL,
                                   responses_count  INTEGER DEFAULT 0,
                                   created_at       TEXT    DEFAULT CURRENT_TIMESTAMP,
                                   updated_at       TEXT
                               )
                               ''')
            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        """Сохраняет или обновляет запись об откликах в день"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            if self.id:
                # Обновляем существующую запись
                cursor = await conn.execute(
                    'UPDATE worker_daily_responses SET responses_count = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (self.responses_count, self.id)
                )
            else:
                # Создаем новую запись
                cursor = await conn.execute(
                    'INSERT INTO worker_daily_responses (worker_id, date, responses_count) VALUES (?, ?, ?)',
                    (self.worker_id, self.date, self.responses_count)
                )
                self.id = cursor.lastrowid
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_by_worker_and_date(cls, worker_id: int, date: str) -> Optional['WorkerDailyResponses']:
        """Получает запись об откликах исполнителя за конкретную дату"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'SELECT * FROM worker_daily_responses WHERE worker_id = ? AND date = ?',
                (worker_id, date)
            )
            record = await cursor.fetchone()
            await cursor.close()

            if record:
                return cls(
                    id=record[0],
                    worker_id=record[1],
                    date=record[2],
                    responses_count=record[3],
                    created_at=record[4],
                    updated_at=record[5]
                )
            return None
        finally:
            await conn.close()

    @classmethod
    async def increment_responses_count(cls, worker_id: int, date: str) -> int:
        """Увеличивает счетчик откликов на 1 и возвращает новое значение"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            # Пытаемся получить существующую запись
            existing = await cls.get_by_worker_and_date(worker_id, date)

            if existing:
                # Обновляем существующую запись
                existing.responses_count += 1
                await existing.save()
                return existing.responses_count
            else:
                # Создаем новую запись
                new_record = cls(worker_id=worker_id, date=date, responses_count=1)
                await new_record.save()
                return 1
        finally:
            await conn.close()

    @classmethod
    async def get_responses_count(cls, worker_id: int, date: str) -> int:
        """Получает количество откликов исполнителя за конкретную дату"""
        record = await cls.get_by_worker_and_date(worker_id, date)
        return record.responses_count if record else 0


class WorkerStatus:
    """Модель для хранения статусов исполнителей (ИП, ООО, СЗ)"""

    def __init__(self, id: int = None, worker_id: int = None,
                 has_ip: bool = False, ip_number: str = None,
                 has_ooo: bool = False, ooo_number: str = None,
                 has_sz: bool = False, sz_number: str = None,
                 last_status_check: str = None,
                 created_at: str = None, updated_at: str = None):
        self.id = id
        self.worker_id = worker_id
        self.has_ip = has_ip
        self.ip_number = ip_number
        self.has_ooo = has_ooo
        self.ooo_number = ooo_number
        self.has_sz = has_sz
        self.sz_number = sz_number
        self.last_status_check = last_status_check
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        conn = await aiosqlite.connect('app/data/database/database.db')
        try:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS worker_statuses
                               (
                                   id                INTEGER PRIMARY KEY AUTOINCREMENT,
                                   worker_id         INTEGER NOT NULL UNIQUE,
                                   has_ip            INTEGER DEFAULT 0,
                                   ip_number         TEXT,
                                   has_ooo           INTEGER DEFAULT 0,
                                   ooo_number        TEXT,
                                   has_sz            INTEGER DEFAULT 0,
                                   sz_number         TEXT,
                                   last_status_check TEXT,
                                   created_at        TEXT    NOT NULL,
                                   updated_at        TEXT    NOT NULL
                               )
                               ''')
            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        """Создает или обновляет запись о статусе исполнителя"""
        conn = await aiosqlite.connect('app/data/database/database.db')
        try:
            # Проверяем, есть ли уже запись
            cursor = await conn.execute(
                'SELECT id FROM worker_statuses WHERE worker_id = ?',
                (self.worker_id,)
            )
            existing = await cursor.fetchone()
            await cursor.close()

            if existing:
                # Обновляем существующую запись
                self.updated_at = datetime.now().isoformat()
                await conn.execute('''
                                   UPDATE worker_statuses
                                   SET has_ip            = ?,
                                       ip_number         = ?,
                                       has_ooo           = ?,
                                       ooo_number        = ?,
                                       has_sz            = ?,
                                       sz_number         = ?,
                                       last_status_check = ?,
                                       updated_at        = ?
                                   WHERE worker_id = ?
                                   ''', (self.has_ip, self.ip_number, self.has_ooo, self.ooo_number,
                                         self.has_sz, self.sz_number, self.last_status_check, self.updated_at,
                                         self.worker_id))
            else:
                # Создаем новую запись
                await conn.execute('''
                                   INSERT INTO worker_statuses
                                   (worker_id, has_ip, ip_number, has_ooo, ooo_number, has_sz, sz_number,
                                    last_status_check, created_at, updated_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                   ''', (self.worker_id, self.has_ip, self.ip_number, self.has_ooo, self.ooo_number,
                                         self.has_sz, self.sz_number, self.last_status_check, self.created_at,
                                         self.updated_at))

            await conn.commit()
        finally:
            await conn.close()

    @classmethod
    async def get_by_worker(cls, worker_id: int) -> Optional['WorkerStatus']:
        """Получает статус исполнителя по worker_id"""
        conn = await aiosqlite.connect('app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'SELECT * FROM worker_statuses WHERE worker_id = ?',
                (worker_id,)
            )
            record = await cursor.fetchone()
            await cursor.close()

            if record:
                return cls(
                    id=record[0],
                    worker_id=record[1],
                    has_ip=bool(record[2]),
                    ip_number=record[3],
                    has_ooo=bool(record[4]),
                    ooo_number=record[5],
                    has_sz=bool(record[6]),
                    sz_number=record[7],
                    last_status_check=record[8],
                    created_at=record[9],
                    updated_at=record[10]
                )
            return None
        finally:
            await conn.close()

    @classmethod
    async def get_or_create(cls, worker_id: int) -> 'WorkerStatus':
        """Получает или создает статус для исполнителя"""
        status = await cls.get_by_worker(worker_id)
        if not status:
            status = cls(worker_id=worker_id)
            await status.save()
        return status

    @classmethod
    async def get_all_for_recheck(cls) -> list['WorkerStatus']:
        """Получает все статусы, которые нужно перепроверить (старше 6 месяцев)"""
        conn = await aiosqlite.connect('app/data/database/database.db')
        try:
            from datetime import timedelta
            six_months_ago = (datetime.now() - timedelta(days=180)).isoformat()

            cursor = await conn.execute('''
                                        SELECT *
                                        FROM worker_statuses
                                        WHERE (has_ip = 1 OR has_ooo = 1 OR has_sz = 1)
                                          AND (last_status_check IS NULL OR last_status_check < ?)
                                        ''', (six_months_ago,))

            records = await cursor.fetchall()
            await cursor.close()

            statuses = []
            for record in records:
                statuses.append(cls(
                    id=record[0],
                    worker_id=record[1],
                    has_ip=bool(record[2]),
                    ip_number=record[3],
                    has_ooo=bool(record[4]),
                    ooo_number=record[5],
                    has_sz=bool(record[6]),
                    sz_number=record[7],
                    last_status_check=record[8],
                    created_at=record[9],
                    updated_at=record[10]
                ))
            return statuses
        finally:
            await conn.close()


class WorkerResponseCancellation:
    """Модель для отслеживания отмен откликов исполнителями"""

    def __init__(self, id: int = None, worker_id: int = None, abs_id: int = None,
                 cancelled_at: str = None):
        self.id = id
        self.worker_id = worker_id
        self.abs_id = abs_id
        self.cancelled_at = cancelled_at

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS worker_response_cancellations
                               (
                                   id            INTEGER PRIMARY KEY AUTOINCREMENT,
                                   worker_id     INTEGER NOT NULL,
                                   abs_id        INTEGER NOT NULL,
                                   cancelled_at  TEXT DEFAULT CURRENT_TIMESTAMP
                               )
                               ''')
            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        """Сохраняет запись об отмене отклика"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'INSERT INTO worker_response_cancellations (worker_id, abs_id) VALUES (?, ?)',
                (self.worker_id, self.abs_id)
            )
            self.id = cursor.lastrowid
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_cancellations_by_worker_and_date(cls, worker_id: int, date_from: str) -> int:
        """Получает количество отмен откликов исполнителя с указанной даты"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'SELECT COUNT(*) FROM worker_response_cancellations WHERE worker_id = ? AND cancelled_at >= ?',
                (worker_id, date_from)
            )
            count = (await cursor.fetchone())[0]
            await cursor.close()
            return count
        finally:
            await conn.close()


class WorkerWorkTypeChanges:
    """Модель для отслеживания изменений направлений работы исполнителя"""

    def __init__(self, id: int | None, worker_id: int, changes_count: int = 0,
                 last_change_date: str | None = None, reset_date: str | None = None,
                 pending_selection: bool = False):
        self.id = id
        self.worker_id = worker_id
        self.changes_count = changes_count  # Количество изменений
        self.last_change_date = last_change_date  # Дата последнего изменения
        self.reset_date = reset_date  # Дата когда можно снова изменять (через 30 дней)
        self.pending_selection = pending_selection  # Флаг ожидания выбора после обнуления ранга

    @classmethod
    async def create_table_if_not_exists(cls) -> None:
        """Создает таблицу если она не существует"""
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS worker_work_type_changes
                               (
                                   id               INTEGER PRIMARY KEY AUTOINCREMENT,
                                   worker_id        INTEGER NOT NULL UNIQUE,
                                   changes_count    INTEGER DEFAULT 0,
                                   last_change_date TEXT,
                                   reset_date       TEXT,
                                   pending_selection INTEGER DEFAULT 0,
                                   FOREIGN KEY (worker_id) REFERENCES workers (id)
                               )
                               ''')

            # Создание индекса
            await conn.execute('''
                               CREATE INDEX IF NOT EXISTS idx_worker_work_type_changes_worker_id
                                   ON worker_work_type_changes (worker_id)
                               ''')

            await conn.commit()
        finally:
            await conn.close()

    async def save(self) -> None:
        """Сохраняет или обновляет запись об изменениях направлений"""
        await self.create_table_if_not_exists()
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            if self.id is None:
                # Создание новой записи
                cursor = await conn.execute(
                    'INSERT INTO worker_work_type_changes (worker_id, changes_count, last_change_date, reset_date, pending_selection) VALUES (?, ?, ?, ?, ?)',
                    (self.worker_id, self.changes_count, self.last_change_date, self.reset_date, 1 if self.pending_selection else 0)
                )
                self.id = cursor.lastrowid
            else:
                # Обновление существующей записи
                await conn.execute(
                    'UPDATE worker_work_type_changes SET changes_count = ?, last_change_date = ?, reset_date = ?, pending_selection = ? WHERE id = ?',
                    (self.changes_count, self.last_change_date, self.reset_date, 1 if self.pending_selection else 0, self.id)
                )

            await conn.commit()
        finally:
            await conn.close()

    @classmethod
    async def get_by_worker(cls, worker_id: int) -> Optional['WorkerWorkTypeChanges']:
        """Получает запись об изменениях направлений исполнителя"""
        await cls.create_table_if_not_exists()
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'SELECT * FROM worker_work_type_changes WHERE worker_id = ?',
                (worker_id,)
            )
            record = await cursor.fetchone()
            await cursor.close()

            if record:
                return cls(
                    id=record[0],
                    worker_id=record[1],
                    changes_count=record[2],
                    last_change_date=record[3],
                    reset_date=record[4],
                    pending_selection=bool(record[5]) if len(record) > 5 else False
                )
            return None
        finally:
            await conn.close()

    @classmethod
    async def get_or_create(cls, worker_id: int) -> 'WorkerWorkTypeChanges':
        """Получает существующую запись или создает новую"""
        existing = await cls.get_by_worker(worker_id)
        if existing:
            return existing

        # Создаем новую запись
        new_record = cls(
            id=None,
            worker_id=worker_id,
            changes_count=0,
            last_change_date=None,
            reset_date=None,
            pending_selection=False
        )
        await new_record.save()
        return await cls.get_by_worker(worker_id)

    def can_change_work_types(self) -> tuple[bool, str]:
        """
        Проверяет, может ли исполнитель изменить направления
        Возвращает (можно_изменить, сообщение)
        
        ИЗМЕНЕНО: Убраны лимиты на количество изменений.
        Исполнители могут менять направления без ограничений.
        """
        # ИЗМЕНЕНО: Убраны лимиты на количество изменений.
        # Исполнители могут менять направления без ограничений.
        
        # Всегда разрешаем изменения направлений
        return (
            True,
            "✅ Вы можете изменить направления в любое время"
        )

    async def register_change(self) -> None:
        """Регистрирует изменение направлений"""
        from datetime import datetime, timedelta

        now = datetime.now()

        # Если достигли лимита и прошло 30 дней - сбрасываем
        if self.changes_count >= 3 and self.reset_date:
            reset_date = datetime.strptime(self.reset_date, '%Y-%m-%d %H:%M:%S')
            if now >= reset_date:
                # Сброс счетчика
                self.changes_count = 0

        # Увеличиваем счетчик
        self.changes_count += 1
        self.last_change_date = now.strftime('%Y-%m-%d %H:%M:%S')

        # Если достигли лимита - устанавливаем дату сброса
        if self.changes_count >= 3:
            reset_date = now + timedelta(days=30)
            self.reset_date = reset_date.strftime('%Y-%m-%d %H:%M:%S')

        await self.save()
