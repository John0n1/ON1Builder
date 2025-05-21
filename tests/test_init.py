# LICENSE: MIT // github.com/John0n1/ON1Builder

import unittest

class TestInit(unittest.TestCase):
    def test_import(self):
        try:
            import on1builder.utils
        except ImportError:
            self.fail("Failed to import on1builder.utils")

if __name__ == '__main__':
    unittest.main()
