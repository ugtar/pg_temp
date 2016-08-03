import unittest2

from temp_pg_db import TempDB

import psycopg2


class Psycopg2TestCase(unittest2.TestCase):

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
    unittest2.main()
