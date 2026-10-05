import asyncio

from backend.database.connection import get_engine
from backend.agents.orchestrator import run_orchestrator_async


def test_database():
    engine = get_engine()

    if engine is None:
        print("❌ DATABASE_URL is not configured")
        return False

    try:
        from sqlalchemy import text

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        print("✅ Database connection is working")
        return True

    except Exception as e:
        print("❌ Database connection failed")
        print("Error:", e)
        return False


async def test_style_workflow():
    print("\n🧪 Testing AI style workflow...")

    user_profile = {
        "age": 25,
        "gender": "Male",
        "body_shape": "Rectangle",
        "skin_tone": "Medium",
        "height": 175,
        "weight": 68,
    }

    user_query = (
        "I need a casual office outfit for a male under ₹3000. "
        "I want a shirt and pant that look smart and comfortable "
        "for everyday office wear."
    )

    try:
        result = await run_orchestrator_async(
            user_profile=user_profile,
            user_query=user_query,
        )

        print("✅ Orchestrator executed successfully")

        if result:
            print("✅ Style workflow returned a result")
            print("\nResult type:", type(result).__name__)

            if isinstance(result, dict):
                print("Result keys:", list(result.keys()))

            return True

        print("❌ Style workflow returned an empty result")
        return False

    except Exception as e:
        print("❌ Style workflow failed")
        print("Error:", e)
        return False


async def main():
    print("\n==============================")
    print("   BACKEND INTEGRATION TEST")
    print("==============================\n")

    database_ok = test_database()
    style_ok = await test_style_workflow()

    print("\n==============================")

    if database_ok and style_ok:
        print("✅ DATABASE + AI WORKFLOW PASSED")
    else:
        print("❌ SOME TESTS FAILED")

    print("==============================")


if __name__ == "__main__":
    asyncio.run(main())