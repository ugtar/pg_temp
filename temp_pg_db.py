"""Set up a temporary postgres DB"""
from __future__ import absolute_import, division, unicode_literals
import os
import sys
import atexit
import shutil
import subprocess
import tempfile
import time

__version__ = '0.5'

# Module level TempDB singleton
temp_db = None


def init_temp_db(databases=None, verbosity=0):
    global temp_db
    if not temp_db:
        temp_db = TempDB(databases, verbosity)
        atexit.register(cleanup)
    return temp_db


def cleanup():
    if not temp_db:
        return
    temp_db.cleanup()


class PGSetupError(Exception):
    pass


def printf(msg):
    sys.stdout.write(msg)


class TempDB(object):

    def __init__(self, databases=None, verbosity=0):
        databases = databases or []
        stdout = None
        stderr = None
        if not verbosity:
            f = open(os.devnull, 'wb')
            stdout = f
            stderr = f
        try:
            self.pg_process = None
            self.pg_temp_dir = None

            self.pg_temp_dir = tempfile.mkdtemp(prefix='pg_tmp_')
            self.pg_data_dir = os.path.join(self.pg_temp_dir, 'data')
            os.mkdir(self.pg_data_dir)
            self.pg_socket_dir = os.path.join(self.pg_temp_dir, 'socket')
            os.mkdir(self.pg_socket_dir)
            printf("Creating temp PG server...")
            sys.stdout.flush()
            rc = subprocess.call(['initdb', self.pg_data_dir], stdout=stdout, stderr=stderr) == 0
            if not rc:
                raise PGSetupError("Couldn't initialize temp PG data dir")
            self.pg_process = subprocess.Popen(
                ['postgres', '-F', '-T', '-D', self.pg_data_dir, '-k', self.pg_socket_dir],
                stdout=stdout, stderr=stderr)
            # test connection
            for i in range(5):
                time.sleep(1)
                rc = subprocess.call(['psql', '-d', 'postgres', '-h', self.pg_socket_dir, '-c', "\dt"],
                    stdout=stdout, stderr=stderr) == 0
                if rc:
                    break
            else:
                raise PGSetupError("Couldn't start PG server")
            rc = True
            for db in databases:
                rc = rc and subprocess.call(['psql', '-d', 'postgres', '-h', self.pg_socket_dir, '-c',
                                             "create database %s;" % db], stdout=stdout, stderr=stderr) == 0
            if not rc:
                raise PGSetupError("Couldn't create databases")
            print("done")
            print("(Connect on: `psql -h %s`)" % self.pg_socket_dir)
        except Exception:
            self.cleanup()
            raise

    def cleanup(self):
        if self.pg_process:
            self.pg_process.kill()
            self.pg_process.wait()
        for d in [self.pg_temp_dir]:
            if d:
                shutil.rmtree(d, ignore_errors=True)
