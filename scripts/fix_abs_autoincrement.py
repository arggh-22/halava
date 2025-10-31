#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration to add AUTOINCREMENT to ABS table
"""

import asyncio
import aiosqlite


async def fix_abs_autoincrement():
    db_path = "app/data/database/database.db"

    print("=== FIXING ABS TABLE AUTOINCREMENT ===")

    conn = await aiosqlite.connect(db_path)

    try:
        # 1. Create backup table with AUTOINCREMENT
        print("\n1. Creating new table with AUTOINCREMENT...")
        await conn.execute('''
                           CREATE TABLE abs_new
                           (
                               id             INTEGER PRIMARY KEY AUTOINCREMENT,
                               customer_id    INTEGER                            NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
                               work_type_id   INTEGER REFERENCES work_types (id) NOT NULL,
                               city_id        INTEGER REFERENCES cities (id),
                               photo_path     BLOB,
                               text_path      TEXT                               NOT NULL,
                               date_to_delite DATETIME,
                               relevance      BOOL    DEFAULT (True)             NOT NULL,
                               views          INTEGER DEFAULT (0),
                               count_photo    INTEGER DEFAULT (0)
                           )
                           ''')

        # 2. Copy data from old table to new table
        print("\n2. Copying data from old table...")
        await conn.execute('''
                           INSERT INTO abs_new (customer_id, work_type_id, city_id, photo_path, text_path,
                                                date_to_delite, relevance, views, count_photo)
                           SELECT customer_id,
                                  work_type_id,
                                  city_id,
                                  photo_path,
                                  text_path,
                                  date_to_delite,
                                  relevance,
                                  views,
                                  count_photo
                           FROM abs
                           ORDER BY id
                           ''')

        # 3. Drop old table
        print("\n3. Dropping old table...")
        await conn.execute('DROP TABLE abs')

        # 4. Rename new table
        print("\n4. Renaming new table...")
        await conn.execute('ALTER TABLE abs_new RENAME TO abs')

        # 5. Commit changes
        await conn.commit()

        print("\n[SUCCESS] Migration completed successfully!")

        # 6. Verify the new table structure
        print("\n5. Verifying new table structure...")
        cursor = await conn.execute("PRAGMA table_info(abs)")
        columns = await cursor.fetchall()

        print("   New ABS table columns:")
        for column in columns:
            cid, name, type_name, notnull, default_value, pk = column
            print(f"     {name}: {type_name} {'PRIMARY KEY' if pk else ''} {'NOT NULL' if notnull else 'NULL'}")

        # 7. Check sqlite_sequence
        cursor = await conn.execute('SELECT seq FROM sqlite_sequence WHERE name = "abs"')
        seq_record = await cursor.fetchone()
        if seq_record:
            print(f"\n6. Next ID will be: {seq_record[0] + 1}")

        # 8. Show current data
        cursor = await conn.execute('SELECT COUNT(*) FROM abs')
        count = await cursor.fetchone()
        print(f"\n7. Total records in ABS table: {count[0]}")

        cursor = await conn.execute('SELECT MIN(id), MAX(id) FROM abs')
        min_max = await cursor.fetchone()
        print(f"   ID range: {min_max[0]} to {min_max[1]}")

    except Exception as e:
        print(f"\n[ERROR] Error during migration: {e}")
        await conn.rollback()
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(fix_abs_autoincrement())
# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration to add AUTOINCREMENT to ABS table
"""

import asyncio
import aiosqlite


async def fix_abs_autoincrement():
    db_path = "app/data/database/database.db"

    print("=== FIXING ABS TABLE AUTOINCREMENT ===")

    conn = await aiosqlite.connect(db_path)

    try:
        # 1. Create backup table with AUTOINCREMENT
        print("\n1. Creating new table with AUTOINCREMENT...")
        await conn.execute('''
                           CREATE TABLE abs_new
                           (
                               id             INTEGER PRIMARY KEY AUTOINCREMENT,
                               customer_id    INTEGER                            NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
                               work_type_id   INTEGER REFERENCES work_types (id) NOT NULL,
                               city_id        INTEGER REFERENCES cities (id),
                               photo_path     BLOB,
                               text_path      TEXT                               NOT NULL,
                               date_to_delite DATETIME,
                               relevance      BOOL    DEFAULT (True)             NOT NULL,
                               views          INTEGER DEFAULT (0),
                               count_photo    INTEGER DEFAULT (0)
                           )
                           ''')

        # 2. Copy data from old table to new table
        print("\n2. Copying data from old table...")
        await conn.execute('''
                           INSERT INTO abs_new (customer_id, work_type_id, city_id, photo_path, text_path,
                                                date_to_delite, relevance, views, count_photo)
                           SELECT customer_id,
                                  work_type_id,
                                  city_id,
                                  photo_path,
                                  text_path,
                                  date_to_delite,
                                  relevance,
                                  views,
                                  count_photo
                           FROM abs
                           ORDER BY id
                           ''')

        # 3. Drop old table
        print("\n3. Dropping old table...")
        await conn.execute('DROP TABLE abs')

        # 4. Rename new table
        print("\n4. Renaming new table...")
        await conn.execute('ALTER TABLE abs_new RENAME TO abs')

        # 5. Commit changes
        await conn.commit()

        print("\n[SUCCESS] Migration completed successfully!")

        # 6. Verify the new table structure
        print("\n5. Verifying new table structure...")
        cursor = await conn.execute("PRAGMA table_info(abs)")
        columns = await cursor.fetchall()

        print("   New ABS table columns:")
        for column in columns:
            cid, name, type_name, notnull, default_value, pk = column
            print(f"     {name}: {type_name} {'PRIMARY KEY' if pk else ''} {'NOT NULL' if notnull else 'NULL'}")

        # 7. Check sqlite_sequence
        cursor = await conn.execute('SELECT seq FROM sqlite_sequence WHERE name = "abs"')
        seq_record = await cursor.fetchone()
        if seq_record:
            print(f"\n6. Next ID will be: {seq_record[0] + 1}")

        # 8. Show current data
        cursor = await conn.execute('SELECT COUNT(*) FROM abs')
        count = await cursor.fetchone()
        print(f"\n7. Total records in ABS table: {count[0]}")

        cursor = await conn.execute('SELECT MIN(id), MAX(id) FROM abs')
        min_max = await cursor.fetchone()
        print(f"   ID range: {min_max[0]} to {min_max[1]}")

    except Exception as e:
        print(f"\n[ERROR] Error during migration: {e}")
        await conn.rollback()
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(fix_abs_autoincrement())
