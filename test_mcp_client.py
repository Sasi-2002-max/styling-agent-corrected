import asyncio

from backend.shopping.mcp_client import MCPShoppingClient


async def main():
    async with MCPShoppingClient() as client:
        print("Connected:", client.is_connected)

        tools = await client.list_tools()
        print("\nMCP tools:")
        for tool in tools:
            print(" -", tool)

        products = await client.search_products(
            query="dresses",
            budget=5000,
        )

        print("\nSearch results:")
        for product in products:
            print(product)


if __name__ == "__main__":
    asyncio.run(main())