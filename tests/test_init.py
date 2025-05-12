# LICENSE: MIT // github.com/John0n1/ON1Builder

import unittest

class TestInit(unittest.TestCase):
    def test_import(self):
        try:
            import scripts.python.pyutils
        except ImportError:
            self.fail("Failed to import scripts.python.pyutils")

if __name__ == '__main__':
    unittest.main()
