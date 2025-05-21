# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
from unittest.mock import AsyncMock, patch
from on1builder.__main__ import main, run_bot

def test_main():
    with patch('on1builder.__main__.run_async') as mock_run_async:
        main()
        mock_run_async.assert_called_once()

@pytest.mark.asyncio
async def test_run_bot():
    with patch('on1builder.core.main_core.MainCore', new_callable=AsyncMock) as mock_main_core:
        mock_instance = AsyncMock()
        mock_main_core.return_value = mock_instance
        
        await run_bot()
        
        # Check that the MainCore was instantiated and run was called
        mock_main_core.assert_called_once()
        mock_instance.run.assert_called_once()
