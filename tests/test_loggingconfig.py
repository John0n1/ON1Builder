# LICENSE: MIT // github.com/John0n1/ON1Builder

import pytest
from unittest.mock import patch
import logging
from scripts.python.logger_on1 import setup_logging

@pytest.fixture
def logger():
    return setup_logging("TestLogger", level=logging.DEBUG)

def test_setup_logging(logger):
    assert logger.name == "TestLogger"
    assert logger.level == logging.DEBUG

def test_logging_output(logger, capsys):
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

    captured = capsys.readouterr()
    assert "Debug message" in captured.out
    assert "Info message" in captured.out
    assert "Warning message" in captured.out
    assert "Error message" in captured.out
    assert "Critical message" in captured.out

def test_spinner_task():
    with patch('python.logger_on1.sys.stdout.write') as mock_write, \
         patch('python.logger_on1.sys.stdout.flush') as mock_flush, \
         patch('python.logger_on1.time.sleep', side_effect=Exception("Stop")):
        stop_event = patch('threading.Event').start()
        stop_event.is_set.side_effect = [False, False, True]
        try:
            setup_logging.spinner_task("Loading", stop_event)
        except Exception as e:
            assert str(e) == "Stop"
        mock_write.assert_called()
        mock_flush.assert_called()
