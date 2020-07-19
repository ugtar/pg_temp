import unittest

import psycopg2

from pg_temp import TempDB, init_temp_db


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


class InitTempDBTestCase(unittest.TestCase):

    def setUp(self):
        self.db = init_temp_db(databases=['test_db'], verbosity=1)

    def tearDown(self):
        self.db.cleanup()

    def test_db_connection(self):
        connection = psycopg2.connect(host=self.db.pg_socket_dir,
                                      database='test_db')
        self.assertTrue(connection)
        connection.close()


if __name__ == '__main__':
    unittest.main()
