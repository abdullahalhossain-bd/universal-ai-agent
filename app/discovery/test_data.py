from sqlalchemy import create_engine, text

from app.core.config import settings


def create_demo_tables():

    engine = create_engine(
        settings.database_url
    )

    with engine.begin() as conn:

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS products (
                id VARCHAR(100) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                price NUMERIC(12,2),
                stock INTEGER,
                image_url TEXT
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS product_images (
                image_id SERIAL PRIMARY KEY,
                product_id VARCHAR(100),
                image_url TEXT
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS inventory (
                inventory_id SERIAL PRIMARY KEY,
                product_id VARCHAR(100),
                quantity INTEGER
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255)
            )
        """))

        conn.execute(text("""
            INSERT INTO products (
                id,
                name,
                description,
                price,
                stock,
                image_url
            )
            VALUES
            (
                'P001',
                'Nike Air Max',
                'Running shoe',
                4999,
                17,
                'https://store.example.com/nike.jpg'
            ),
            (
                'P002',
                'Adidas Runner',
                'Lightweight shoe',
                3999,
                8,
                'https://store.example.com/adidas.jpg'
            )
            ON CONFLICT (id) DO NOTHING
        """))

        conn.execute(text("""
            INSERT INTO product_images (
                product_id,
                image_url
            )
            VALUES
            (
                'P001',
                'https://store.example.com/nike-2.jpg'
            ),
            (
                'P002',
                'https://store.example.com/adidas-2.jpg'
            )
        """))

        conn.execute(text("""
            INSERT INTO inventory (
                product_id,
                quantity
            )
        VALUES
            ('P001', 17),
            ('P002', 8)
        """))

    engine.dispose()
