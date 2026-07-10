import asyncio
import logging
from typing import List, Dict, Any

try:
    from notebooklm import NotebookLM
except ImportError:
    logging.warning("notebooklm-py is not installed. Please install it to use NotebookLMTool.")
    NotebookLM = None

class NotebookLMToolError(Exception):
    """Base exception for NotebookLM tool."""
    pass

class NotebookLMAuthError(NotebookLMToolError):
    """Raised when authentication (session/cookies) fails or expires."""
    pass

class NotebookLMUpstreamError(NotebookLMToolError):
    """Raised when Google changes undocumented endpoints and the library breaks."""
    pass

class NotebookLMTool:
    """
    A wrapper around notebooklm-py for programmatic agent access to NotebookLM.
    Fails loudly if undocumented endpoints change.
    """
    def __init__(self):
        if NotebookLM is None:
            raise NotebookLMToolError("notebooklm-py is not installed. Run 'pip install -r requirements.txt'")

    async def _execute_with_health_check(self, coro):
        """
        Executes a coroutine and distinguishes between auth errors vs upstream breakage.
        """
        try:
            return await coro
        except Exception as e:
            err_msg = str(e).lower()
            if "auth" in err_msg or "cookie" in err_msg or "unauthorized" in err_msg or "401" in err_msg or "session" in err_msg:
                raise NotebookLMAuthError(f"Session expired or auth failed. Please re-run 'notebooklm login' or extract fresh cookies. Error: {e}")
            elif "parse" in err_msg or "attribute" in err_msg or "keyerror" in err_msg or "404" in err_msg or "endpoint" in err_msg:
                raise NotebookLMUpstreamError(f"NotebookLM API endpoint changed - upstream breakage. The unofficial library may need an update. Error: {e}")
            else:
                raise NotebookLMToolError(f"NotebookLM operation failed: {e}")

    async def notebook_create(self, name: str) -> str:
        """Creates a new notebook and returns its ID."""
        async with NotebookLM() as nlm:
            notebook = await self._execute_with_health_check(nlm.create_notebook(name=name))
            return notebook.id

    async def notebook_list(self) -> List[Dict[str, Any]]:
        """Lists existing notebooks."""
        async with NotebookLM() as nlm:
            notebooks = await self._execute_with_health_check(nlm.get_notebooks())
            return [{"id": nb.id, "name": nb.name} for nb in notebooks]

    async def source_add(self, notebook_id: str, content: str) -> str:
        """Adds a source to the specified notebook."""
        # Note: Depending on notebooklm-py version, adding a source by raw text or URL can differ.
        # This uses a generic approach assuming text source addition.
        async with NotebookLM() as nlm:
            notebooks = await self._execute_with_health_check(nlm.get_notebooks())
            notebook = next((nb for nb in notebooks if nb.id == notebook_id), None)
            if not notebook:
                raise NotebookLMToolError(f"Notebook {notebook_id} not found.")
            
            # Add a text document as a source (assuming add_document exists)
            # The exact method depends on the library. We will attempt add_document.
            try:
                source = await self._execute_with_health_check(notebook.add_document(text=content))
                return getattr(source, 'id', 'unknown_id')
            except AttributeError:
                # Fallback if the API method is different
                raise NotebookLMUpstreamError("The 'add_document' method is missing. The notebooklm-py API might have changed.")

    async def notebook_query(self, notebook_id: str, query: str) -> str:
        """Queries the specified notebook and returns the cited answer."""
        async with NotebookLM() as nlm:
            notebooks = await self._execute_with_health_check(nlm.get_notebooks())
            notebook = next((nb for nb in notebooks if nb.id == notebook_id), None)
            if not notebook:
                raise NotebookLMToolError(f"Notebook {notebook_id} not found.")
            
            response = await self._execute_with_health_check(notebook.query(query))
            return response.text if hasattr(response, 'text') else str(response)

    async def notebook_delete(self, notebook_id: str) -> bool:
        """Deletes the specified notebook."""
        async with NotebookLM() as nlm:
            notebooks = await self._execute_with_health_check(nlm.get_notebooks())
            notebook = next((nb for nb in notebooks if nb.id == notebook_id), None)
            if not notebook:
                return False
            await self._execute_with_health_check(notebook.delete())
            return True
