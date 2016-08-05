import sys
import psycopg2

from pg_temp import TempDB

# Import unittest2 for older python versions
if sys.version_info < (2, 7):
    import unittest2 as unittest
else:
    import unittest


class Psycopg2TestCase(unittest.TestCase):

    def setUp(self):
        self.db = TempDB(databases=['test_db'], verbosity=1)

    def tearDown(self):
        self.db.cleanup()

    def test_db_connection(self):
        connection = psycopg2.connect(host=self.db.pg_socket_dir,
                                      database='test_db')
        self.assertTrue(connection)
        connection.close()


if __name__ == '__main__':
    unittest.main()
