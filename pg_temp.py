"""Set up a temporary postgres DB"""
from __future__ import absolute_import, division, unicode_literals
import os
import sys
import atexit
import shutil
import subprocess
import tempfile
import time
import pwd
from contextlib import contextmanager

if sys.version_info < (3, 3):
    from pipes import quote
else:
    from shlex import quote

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


@contextmanager
def check_user():
    # If running as root, try to run the db server creation as postgres
    # user (assumed to exist)
    run_as = lambda x: x
    current_euid = os.geteuid()
    current_egid = os.getegid()
    current_user = pwd.getpwuid(current_euid).pw_name
    if current_euid == 0:
        try:
            # try to find the postgres user
            name = pwd.getpwnam('postgres')
        except KeyError:
            raise PGSetupError("Can't create DB server as root, and "
                               "there's no postgres user!")
        run_as = lambda cmd: ['su', '-', 'postgres', '-c',
                              ' '.join(quote(c) for c in cmd)]
        # Note: we can't just seteuid because the postgres server process
        # checks that euid == uid and that euid is not 0
        # http://doxygen.postgresql.org/main_8c.html#a0bd2ee2e17615192912a97c16f908ac2
        os.setegid(name.pw_gid)
        os.seteuid(name.pw_uid)
    try:
        yield run_as, current_user
    finally:
        os.seteuid(current_euid)
        os.setegid(current_egid)


class PGSetupError(Exception):
    pass


def printf(msg):
    sys.stdout.write(msg)


class TempDB(object):

    def __init__(self,
                 databases=None,
                 verbosity=0,
                 retry=5,
                 tincr=1.0,
                 initdb='initdb',
                 postgres='postgres',
                 psql='psql',
                 createuser='createuser'):
        """Initialize a temporary Postgres database

        :param databases: list of databases to create
        :param verbosity: verbosity level, non-zero values print messages
        :param retry: number of times to retry a connection
        :param tincr: how much time to wait between retries
        :param initdb: path to `initdb`, defaults to first in $PATH
        :param postgres: path to `postgres`, defaults to first in $PATH
        :param psql: path to `psql`, defaults to first in $PATH

        """
        with check_user() as (run_as, user_name):
            self._setup(databases, verbosity, retry, tincr, initdb, postgres,
                        psql, createuser, run_as, user_name)

    def _setup(self, databases, verbosity, retry, tincr, initdb, postgres,
               psql, createuser, run_as, user_name):

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
            rc = subprocess.call(run_as([initdb, self.pg_data_dir]),
                                 stdout=stdout, stderr=stderr) == 0
            if not rc:
                raise PGSetupError("Couldn't initialize temp PG data dir")
            self.pg_process = subprocess.Popen(
                run_as([postgres, '-F', '-T',
                        '-D', self.pg_data_dir,
                        '-k', self.pg_socket_dir,
                        '-h', '']),
                stdout=stdout, stderr=stderr)

            # test connection
            for i in range(retry):
                time.sleep(tincr)
                rc = subprocess.call(run_as([psql, '-d', 'postgres',
                                             '-h', self.pg_socket_dir,
                                             '-c', "\dt"]),
                                     stdout=stdout, stderr=stderr) == 0
                if rc:
                    break
            else:
                raise PGSetupError("Couldn't start PG server")
            rc = subprocess.call(run_as([createuser,
                                         '-h', self.pg_socket_dir,
                                         user_name, '-s']),
                                 stdout=stdout, stderr=stderr) == 0
            if not rc:
                # maybe the user already exists, and that's ok
                pass
            rc = True
            for db in databases:
                rc = rc and subprocess.call(
                    run_as([psql, '-d', 'postgres',
                            '-h', self.pg_socket_dir,
                            '-c', "create database %s;" % db]),
                    stdout=stdout, stderr=stderr) == 0
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
