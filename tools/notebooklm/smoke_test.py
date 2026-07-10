import asyncio
import logging
from notebooklm_tool import NotebookLMTool

logging.basicConfig(level=logging.INFO)

async def main():
    print("=== NotebookLM Integration Smoke Test ===")
    tool = NotebookLMTool()
    notebook_id = None
    
    try:
        # 1. Create test notebook
        print("Creating notebook 'antigravity-integration-test'...")
        notebook_id = await tool.notebook_create("antigravity-integration-test")
        print(f"Created notebook with ID: {notebook_id}")
        
        # 2. Add source
        print("Adding source content to notebook...")
        content = "SummitOS is a commercial transportation platform. Any screen visible to a driver, dispatcher, or customer must never expose passenger PII beyond what is operationally necessary."
        source_id = await tool.source_add(notebook_id, content)
        print(f"Added source with ID: {source_id}")
        
        # 3. Run query
        print("Querying notebook...")
        answer = await tool.notebook_query(notebook_id, "What is SummitOS and what are the PII rules?")
        print(f"\n--- Query Answer ---\n{answer}\n--------------------\n")
        
    except Exception as e:
        print(f"\n[ERROR] Smoke test failed: {e}")
        
    finally:
        # 4. Clean up notebook
        if notebook_id:
            print(f"Cleaning up: deleting notebook {notebook_id}...")
            deleted = await tool.notebook_delete(notebook_id)
            if deleted:
                print("Cleanup successful.")
            else:
                print("Failed to delete notebook during cleanup.")

if __name__ == "__main__":
    asyncio.run(main())
