import os
import sys
import traceback

URL = "postgresql://agent:agent_password@localhost:5432/agent_db"

print("=" * 70)
print("POSTGRESQL DATASOURCE DIAGNOSTIC")
print("=" * 70)

print("\n[1] Python")
print(sys.executable)
print(sys.version)

print("\n[2] Environment")
print("ALLOW_LOCAL_DATASOURCE_HOSTS =", repr(
    os.getenv("ALLOW_LOCAL_DATASOURCE_HOSTS")
))

print("\n[3] Raw SQLAlchemy connection")
try:
    from sqlalchemy import create_engine, text

    engine = create_engine(
        "postgresql+psycopg://agent:agent_password@localhost:5432/agent_db",
        pool_pre_ping=True,
    )

    print("ENGINE URL:", engine.url)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()

    print("RAW SQLAlchemy RESULT:", result)
    print("RAW SQLAlchemy: OK")

except Exception as e:
    print("RAW SQLAlchemy: FAILED")
    print("TYPE:", type(e).__name__)
    print("MESSAGE:", str(e))
    traceback.print_exc()


print("\n[4] Network guard")
try:
    from app.core.network_guard import assert_safe_connection_host

    assert_safe_connection_host(URL)

    print("NETWORK GUARD: OK")

except Exception as e:
    print("NETWORK GUARD: FAILED")
    print("TYPE:", type(e).__name__)
    print("MESSAGE:", str(e))
    traceback.print_exc()


print("\n[5] ConnectorFactory")
try:
    from app.connectors.factory import ConnectorFactory

    connector = ConnectorFactory.create(
        "postgresql",
        URL,
    )

    print("CONNECTOR TYPE:", type(connector))
    print("CONNECTOR ENGINE:", connector.engine.url)

except Exception as e:
    print("CONNECTOR FACTORY: FAILED")
    print("TYPE:", type(e).__name__)
    print("MESSAGE:", str(e))
    traceback.print_exc()
    connector = None


print("\n[6] PostgreSQLConnector.test_connection()")
try:
    import asyncio

    if connector is None:
        raise RuntimeError("connector was not created")

    result = asyncio.run(
        connector.test_connection()
    )

    print("CONNECTOR TEST RESULT:", result)

except Exception as e:
    print("CONNECTOR TEST: FAILED")
    print("TYPE:", type(e).__name__)
    print("MESSAGE:", str(e))
    traceback.print_exc()


print("\n[7] DataSourceService._test_connection_sync()")
try:
    from app.datasources.service import DataSourceService
    from app.db.database import SessionLocal

    db = SessionLocal()

    try:
        service = DataSourceService(db)

        result = service._test_connection_sync(
            "postgresql",
            URL,
        )

        print("SERVICE DIRECT RESULT:", result)

    finally:
        db.close()

except Exception as e:
    print("DATASOURCE SERVICE: FAILED")
    print("TYPE:", type(e).__name__)
    print("MESSAGE:", str(e))
    traceback.print_exc()


print("\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)
