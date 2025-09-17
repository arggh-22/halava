import json
import logging
import sqlite3
from datetime import date, datetime
from random import randint
from typing import Optional
import aiosqlite

from app.untils import help_defs
from telegraph import Telegraph


telegraph = Telegraph()
logger = logging.getLogger()


class Customer:
    def __init__(self, id: int | None, tg_id: int, city_id: int, tg_name: str, abs_count: int = None, access_token: str = None, author_name: str = None):
        self.id = id
        self.tg_id = tg_id
        self.city_id = city_id
        self.tg_name = tg_name
        self.abs_count = abs_count
        self.access_token = access_token
        self.author_name = author_name

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            result = telegraph.create_account(short_name=f'customer_{self.tg_id}', author_name='haltura customer',
                                              author_url='https://t.me/Rus_haltura_bot')
            cursor = await conn.execute('INSERT INTO customers (tg_id, city_id, tg_name, access_token, author_name) VALUES (?, ?, ?, ?, ?)',
                                        (self.tg_id, self.city_id, self.tg_name, result['access_token'], result['author_name']))
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
                return cls(id=record[0], city_id=record[1], tg_id=record[2], tg_name=record[3], abs_count=record[4], access_token=record[5], author_name=record[6])
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
                return [cls(id=record[0], city_id=record[1], tg_id=record[2], tg_name=record[3], abs_count=record[4], access_token=record[5], author_name=record[6])
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
            return [cls(id=record[0], city_id=record[1], tg_id=record[2], tg_name=record[3], abs_count=record[4], access_token=record[5], author_name=record[6]) for
                    record in records]
        finally:
            await conn.close()

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
                 portfolio_photo: dict = None):
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

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            city_id = [str(x) for x in self.city_id]
            city_id = ' | '.join(city_id)
            cursor = await conn.execute(
                'INSERT INTO workers (tg_id, tg_name, city_id, phone_number, confirmation_code, ref_code, registration_data) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (self.tg_id, self.tg_name, city_id, self.phone_number, self.confirmation_code, self.tg_id, self.registration_data))
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_worker(cls, id: int = None, tg_id: int = None, ref_code: int = None) -> Optional['Worker'] | None:
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
                        portfolio_photo=json.loads(record[19]) if record[19] else None
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
                            portfolio_photo=json.loads(record[19]) if record[19] else None
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
        Оптимизированный метод для получения активных исполнителей по городу и типу работы.
        Используется только для рассылки объявлений.
        """
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            # SQL запрос с фильтрацией в базе данных
            query = '''
            SELECT w.*, ws.work_type_ids, ws.unlimited_work_types 
            FROM workers w
            LEFT JOIN worker_and_subscription ws ON w.id = ws.worker_id
            WHERE w.active = 1 
            AND w.city_id LIKE ?
            '''
            cursor = await conn.execute(query, [f'%{city_id}%'])
            records = await cursor.fetchall()
            await cursor.close()

            matching_workers = []
            work_type_id_str = str(work_type_id)
            
            for record in records:
                # Проверяем city_id (формат: "1 | 2 | 3")
                record_city_ids = record[4].split(' | ')
                if str(city_id) not in record_city_ids:
                    continue
                
                # Проверяем подписку и тип работы
                work_type_ids = record[20].split('|') if record[20] else []
                unlimited_work_types = record[21] if record[21] is not None else False
                
                # Если не подходит по типу работы - пропускаем
                if not unlimited_work_types and work_type_id_str not in work_type_ids:
                    continue
                
                worker = cls(
                    id=record[0],
                    tg_id=record[1],
                    tg_name=record[2],
                    phone_number=record[3],
                    city_id=[int(x) for x in record_city_ids],
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
                )
                matching_workers.append(worker)

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
            cursor = await conn.execute('SELECT COUNT(1) FROM ban_list WHERE COALESCE(ban_now, 0) = 1 OR COALESCE(forever, 0) = 1')
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


class SubscriptionType:
    def __init__(self, id: int | None, subscription_type: str, count_work_types: int,
                 count_guaranteed_orders: int, notification: bool, unlimited: bool, price: int, count_cites: int):
        self.id = id
        self.subscription_type = subscription_type
        self.count_work_types = count_work_types
        self.count_guaranteed_orders = count_guaranteed_orders
        self.notification = notification
        self.unlimited = unlimited
        self.price = price
        self.count_cites = count_cites

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'INSERT INTO subscription_types (subscription_type, count_work_types, count_guaranteed_orders, notification, unlimited, price, count_cites) VALUES (?, ?, ?, ?, ?, ?, ?)',
                [self.subscription_type, self.count_work_types, self.count_guaranteed_orders, self.notification, self.unlimited, self.price])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def update(self, count_work_types: int = None, count_guaranteed_orders: int = None,
                     notification: bool = None, unlimited: bool = None, price: int = None) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            updates = []
            params = []

            if count_work_types is not None:
                updates.append('count_work_types = ?')
                params.append(count_work_types)

            if count_guaranteed_orders is not None:
                updates.append('count_guaranteed_orders = ?')
                params.append(count_guaranteed_orders)

            if notification is not None:
                updates.append('notification = ?')
                params.append(notification)

            if unlimited is not None:
                updates.append('unlimited = ?')
                params.append(unlimited)

            if price is not None:
                updates.append('price = ?')
                params.append(price)

            if updates:
                params.append(self.id)
                query = f"UPDATE subscription_types SET {', '.join(updates)} WHERE id = ?"
                await conn.execute(query, params)
                await conn.commit()
        finally:
            await conn.close()

    @classmethod
    async def get_subscription_type(cls, id: int = None) -> Optional['SubscriptionType']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM subscription_types WHERE id = ?', [id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(
                    id=record[0],
                    subscription_type=record[1],
                    count_work_types=record[2],
                    count_guaranteed_orders=record[3],
                    notification=True if record[4] == 1 else False,
                    unlimited=True if record[5] == 1 else False,
                    price=record[6],
                    count_cites=record[7]
                )
            return None
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['SubscriptionType'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM subscription_types')
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [
                    cls(
                        id=record[0],
                        subscription_type=record[1],
                        count_work_types=record[2],
                        count_guaranteed_orders=record[3],
                        notification=True if record[4] == 1 else False,
                        unlimited=True if record[5] == 1 else False,
                        price=record[6],
                        count_cites=record[7]
                    )
                    for record in records
                ]
            return None
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


class WorkSubType:
    def __init__(self, id: int | None, work_mine_type_id: int, work_type: str, template: str | None,
                 template_photo: str | None):
        self.id = id
        self.work_mine_type_id = work_mine_type_id
        self.work_type = work_type
        self.template = template
        self.template_photo = template_photo

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('INSERT INTO work_sub_types (work_mine_type_id, work_type) VALUES (?, ?)',
                                        [self.work_mine_type_id, self.work_type])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def delete(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('DELETE FROM work_sub_types WHERE id = ?', [self.id])
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    @classmethod
    async def get_work_type(cls, id: int = None, work_type: str = None) -> Optional['WorkSubType'] | None:
        if id or work_type:
            conn = await aiosqlite.connect(database='app/data/database/database.db')
            try:
                cursor = await conn.execute('SELECT * FROM work_sub_types WHERE id = ?', [id])
                record = await cursor.fetchone()
                await cursor.close()
                if record:
                    return cls(id=record[0], work_mine_type_id=record[1], work_type=record[2], template=record[3],
                               template_photo=record[4])
                return None
            finally:
                await conn.close()
        else:
            return None

    @classmethod
    async def get_work_sub_types(cls, work_mine_type_id: int) -> list['WorkSubType'] | None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM work_sub_types WHERE work_mine_type_id = ?', [work_mine_type_id])
            records = await cursor.fetchall()
            await cursor.close()
            if records:
                return [cls(id=record[0], work_mine_type_id=record[1], work_type=record[2], template=record[3],
                            template_photo=record[4]) for record in records]
            return None
        finally:
            await conn.close()

    @classmethod
    async def get_all(cls) -> list['WorkSubType']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM work_sub_types')
            records = await cursor.fetchall()
            await cursor.close()
            return [cls(id=record[0], work_mine_type_id=record[1], work_type=record[2], template=record[3],
                        template_photo=record[4]) for record in records]
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
            await conn.commit()
            await cursor.close()
        finally:
            await conn.close()

    async def delete(self, delite_photo: bool) -> None:
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
                self.date_to_delite += datetime.strptime(str(date_to_delite), '%Y-%m-%d %H:%M:%S.%f')
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
                        photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if record[4] == 'null' else {'0': record[4]},
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
                            photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if record[4] == 'null' else {'0': record[4]},
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
                            photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if record[4] == 'null' else {'0': record[4]},
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
                           photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if record[4] == 'null' else {'0': record[4]},
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
    def __init__(self, worker_id: int, id: int = None, subscription_id: int = None,
                 guaranteed_orders: int = None, subscription_end: str = None, work_type_ids: list = None,
                 unlimited_orders: bool = None, unlimited_work_types: bool = None, notification: bool = False):
        self.id = id
        self.worker_id = worker_id
        self.subscription_id = subscription_id
        self.guaranteed_orders = guaranteed_orders
        self.date_end = datetime.strptime(subscription_end, "%Y-%m-%d") if subscription_end else None
        self.subscription_end = self.date_end.strftime("%d.%m.%Y") if subscription_end else None
        self.work_type_ids = work_type_ids
        self.unlimited_orders = unlimited_orders
        self.unlimited_work_types = unlimited_work_types
        self.notification = notification

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            cursor = await conn.execute(
                'INSERT INTO worker_and_subscription (worker_id) VALUES (?)',
                [self.worker_id])
            await conn.commit()
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

    async def update(self, subscription_id: int = None, guaranteed_orders: int = None,
                     subscription_end: date = None, work_type_ids: list = None,
                     unlimited_orders: bool = None, unlimited_work_types: bool = None,
                     notification: bool = None) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db',
                                       detect_types=sqlite3.PARSE_DECLTYPES |
                                                    sqlite3.PARSE_COLNAMES)
        try:
            updates = []
            params = []

            if subscription_id is not None:
                updates.append('subscription_id = ?')
                params.append(subscription_id)

            if guaranteed_orders is not None:
                updates.append('guaranteed_orders = ?')
                params.append(guaranteed_orders)

            if subscription_end is not None:
                updates.append('subscription_end = ?')
                params.append(subscription_end)

            if work_type_ids is not None:
                updates.append('work_type_ids = ?')
                work_type_ids = '|'.join(work_type_ids)
                params.append(work_type_ids)

            if unlimited_orders is not None:
                updates.append('unlimited_orders = ?')
                params.append(unlimited_orders)

            if unlimited_work_types is not None:
                updates.append('unlimited_work_types = ?')
                params.append(unlimited_work_types)

            if notification is not None:
                updates.append('notification = ?')
                params.append(notification)

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
                        subscription_id=record[2],
                        guaranteed_orders=record[3],
                        subscription_end=record[4],
                        work_type_ids=record[5].split('|') if record[5] else None,
                        unlimited_orders=record[6],
                        unlimited_work_types=record[7])
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
            record = await cursor.fetchall()
            await cursor.close()
            return cls(id=record[0][0],
                       worker_id=record[0][1],
                       subscription_id=record[0][2],
                       guaranteed_orders=record[0][3],
                       subscription_end=record[0][4],
                       work_type_ids=record[0][5].split('|') if record[0][5] else None,
                       unlimited_orders=record[0][6],
                       unlimited_work_types=record[0][7])
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
                       subscription_id=record[0][2],
                       guaranteed_orders=record[0][3],
                       subscription_end=record[0][4],
                       work_type_ids=record[0][5].split('|') if record[0][5] else None,
                       unlimited_orders=record[0][6],
                       unlimited_work_types=record[0][7])
        finally:
            await conn.close()


class WorkersAndAbs:
    def __init__(self, worker_id: int, abs_id: int, id: int = None, applyed: bool = None, send_by_worker: int = None,
                 send_by_customer: int = None, customer_messages: str = None, worker_messages: str = None, turn: bool = True):
        self.id = id
        self.worker_id = worker_id
        self.abs_id = abs_id
        self.send_by_worker = send_by_worker
        self.send_by_customer = send_by_customer
        self.applyed = applyed
        step = 0
        if worker_messages:
            if len(worker_messages) > 1024:
                step = int(((len(worker_messages) - 1024) / 20))
            elif customer_messages:
                if len(customer_messages) > 1024:
                    step = int(((len(customer_messages) - 1024) / 20))
            self.worker_messages = (worker_messages.split(' | '))[step::]
        else:
            self.worker_messages = ['Исполнитель не отправил сообщение']

        if customer_messages is None:
            if applyed:
                self.customer_messages = []
            else:
                self.customer_messages = []
        else:
            self.customer_messages = (customer_messages.split(' | '))[step::]
        self.turn = turn

    async def save(self) -> None:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute(
                'INSERT INTO workers_and_abs (worker_id, abs_id) VALUES (?, ?)',
                [self.worker_id, self.abs_id])
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
                     customer_messages: list = None, turn: bool = None) -> None:
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
                        turn=True if record[8] == 1 else False)
                    for record in records]
        finally:
            await conn.close()

    @classmethod
    async def get_by_worker(cls, worker_id: int) -> list['WorkersAndAbs']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM workers_and_abs WHERE worker_id = ? ', [worker_id])
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
                        turn=True if record[8] == 1 else False
                        )
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
                        turn=True if record[8] == 1 else False
                        )
                    for record in records]
        finally:
            await conn.close()

    @classmethod
    async def get_by_worker_and_abs(cls, worker_id: int, abs_id: int) -> Optional['WorkersAndAbs']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM workers_and_abs WHERE worker_id = ? and abs_id = ?',
                                        [worker_id, abs_id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(id=record[0],
                           worker_id=record[1],
                           abs_id=record[2],
                           send_by_worker=record[3],
                           send_by_customer=record[4],
                           applyed=True if record[5] == 1 else False,
                           worker_messages=record[6],
                           customer_messages=record[7],
                           turn=True if record[8] == 1 else False
                           )
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
                        photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if record[4] == 'null' else {'0': record[4]},
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
                            photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if record[4] == 'null' else {'0': record[4]},
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
                           photo_path=None if not record[4] else json.loads(record[4]) if '{' in record[4] else None if record[4] == 'null' else {'0': record[4]},
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
    def __init__(self, id: int | None, user_tg_id: int, user_messages: str, admin_messages: str = None, turn: bool = True):
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
                return [cls(id=record[0], user_tg_id=record[1], user_messages=record[2], admin_messages=record[3], turn=True if record[4] == 1 else False) for record in records]
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
                return cls(id=record[0], user_tg_id=record[1], user_messages=record[2], admin_messages=record[3], turn=True if record[4] == 1 else False)
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
                return cls(id=record[0], user_tg_id=record[1], user_messages=record[2], admin_messages=record[3], turn=True if record[4] == 1 else False)
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
    def __init__(self, worker_id: int,  abs_id: int, id: int = None):
        self.id = id
        self.abs_id = abs_id
        self.worker_id = worker_id

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

    @classmethod
    async def get_by_worker_and_abs(cls, worker_id: int, abs_id: int) -> Optional['WorkerAndReport']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM worker_and_report WHERE worker_id = ? and abs_id = ?',
                                        [worker_id, abs_id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(id=record[0],
                           worker_id=record[1],
                           abs_id=record[2])
        finally:
            await conn.close()

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
    def __init__(self, worker_id: int,  abs_id: int, id: int = None):
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

    @classmethod
    async def get_by_worker_and_abs(cls, worker_id: int, abs_id: int) -> Optional['WorkerAndBadResponse']:
        conn = await aiosqlite.connect(database='app/data/database/database.db')
        try:
            cursor = await conn.execute('SELECT * FROM worker_and_bad_response WHERE worker_id = ? and abs_id = ?',
                                        [worker_id, abs_id])
            record = await cursor.fetchone()
            await cursor.close()
            if record:
                return cls(id=record[0],
                           worker_id=record[1],
                           abs_id=record[2])
        finally:
            await conn.close()

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
    def __init__(self, questions: list,  answer: str, id: int = None):
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
