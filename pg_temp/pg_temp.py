"""Set up a temporary postgres DB"""
import itertools
import os
import sys
import atexit
import shutil
import subprocess
import tempfile
import time
import pwd
from contextlib import contextmanager
from shlex import quote


# Module level TempDB singleton
temp_db = None


def flatten(listOfLists):
    return itertools.chain.from_iterable(listOfLists)


def init_temp_db(*args, **kwargs):
    global temp_db
    if not temp_db:
        temp_db = TempDB(*args, **kwargs)
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


class TempDB(object):

    def __init__(self,
                 databases=None,
                 verbosity=1,
                 retry=5,
                 tincr=1.0,
                 initdb='initdb',
                 postgres='postgres',
                 psql='psql',
                 createuser='createuser',
                 dirname=None,
                 sock_dir=None,
                 options=None):
        """Initialize a temporary Postgres database

        :param databases: list of databases to create
        :param verbosity: verbosity level, larger values are more verbose
        :param retry: number of times to retry a connection
        :param tincr: how much time to wait between retries
        :param initdb: path to `initdb`, defaults to first in $PATH
        :param postgres: path to `postgres`, defaults to first in $PATH
        :param psql: path to `psql`, defaults to first in $PATH
        :param dirname: override temp data directory generation and create the
            db in `dirname`
        :param sock_dir: specify the postgres socket directory
        :param options: a dictionary of configuration params and values
            passed to `postgres` with `-c`

        """
        self.verbosity = verbosity
        self.pg_process = None
        with check_user() as (run_as, user_name):
            options = dict() if not options else options
            self._setup(databases, retry, tincr, initdb, postgres, sock_dir,
                        psql, createuser, run_as, user_name, dirname, options)

    def stdout(self, level):
        """Return file handle for stdout for the current verbosity"""
        if level > self.verbosity:
            return open(os.devnull, 'wb')
        else:
            return sys.stdout

    def stderr(self, level):
        """Return file handle for stderr for the current verbosity"""
        if level > self.verbosity:
            return open(os.devnull, 'wb')
        else:
            return sys.stderr

    def printf(self, msg, level=1):
        if level > self.verbosity:
            return
        print(msg)

    def _setup(self, databases, retry, tincr, initdb, postgres, sock_dir,
               psql, createuser, run_as, user_name, dirname, options):

        databases = databases or []
        try:
            self.printf("Creating temp PG server...")
            self._setup_directories(dirname, sock_dir)
            self.create_db_server(run_as, initdb, postgres, options)
            self.test_connection(run_as, psql, retry, tincr)
            self.create_user(run_as, user_name, createuser)
            self.create_databases(run_as, psql, databases)
            self.printf("done")
            self.printf("(Connect on: `psql -h %s`)" % self.pg_socket_dir)
        except Exception:
            self.cleanup()
            raise

    def _setup_directories(self, dirname, sock_dir):
        self.pg_temp_dir = None
        if not dirname:
            self.pg_temp_dir = tempfile.mkdtemp(prefix='pg_tmp_')
            dirname = self.pg_temp_dir
        self.pg_data_dir = os.path.join(dirname, 'data')
        os.mkdir(self.pg_data_dir)
        if not sock_dir:
            self.pg_socket_dir = os.path.join(dirname, 'socket')
            os.mkdir(self.pg_socket_dir)
        else:
            self.pg_socket_dir = sock_dir

    def create_db_server(self, run_as, initdb, postgres, options):
        rc = subprocess.call(run_as([initdb, self.pg_data_dir]),
                             stdout=self.stdout(2),
                             stderr=self.stderr(2)) == 0
        if not rc:
            raise PGSetupError("Couldn't initialize temp PG data dir")
        options = ['%s=%s' % (k, v) for (k, v) in options.items()]
        cmd = [postgres, '-F', '-T', '-D', self.pg_data_dir,
               '-k', self.pg_socket_dir, '-h', '']
        cmd += flatten(zip(itertools.repeat('-c'), options))

        self.printf("Running %s" % str(' '.join(cmd)))
        self.pg_process = subprocess.Popen(
            run_as(cmd),
            stdout=self.stdout(2),
            stderr=self.stderr(2))
        return rc

    def test_connection(self, run_as, psql, retry, tincr):
        # test connection
        for i in range(retry):
            time.sleep(tincr)
            rc = subprocess.call(run_as([psql, '-d', 'postgres',
                                         '-h', self.pg_socket_dir,
                                         '-c', r"\dt"]),
                                 stdout=self.stdout(2),
                                 stderr=self.stderr(2)) == 0
            if rc:
                break
        else:
            raise PGSetupError("Couldn't start PG server")
        return rc

    def create_user(self, run_as, user_name, createuser):
        rc = subprocess.call(run_as([createuser,
                                     '-h', self.pg_socket_dir,
                                     user_name, '-s']),
                             stdout=self.stdout(2),
                             stderr=self.stderr(2)) == 0
        if not rc:
            # maybe the user already exists, and that's ok
            pass
        return rc

    def create_databases(self, run_as, psql, databases):
        rc = True
        for db in databases:
            rc = rc and subprocess.call(
                run_as([psql, '-d', 'postgres',
                        '-h', self.pg_socket_dir,
                        '-c', "create database %s;" % db]),
                stdout=self.stdout(2),
                stderr=self.stderr(2)) == 0
        if not rc:
            raise PGSetupError("Couldn't create databases")
        return rc

    def cleanup(self):
        if self.pg_process:
            self.pg_process.kill()
            self.pg_process.wait()
        for d in [self.pg_temp_dir]:
            if d:
                shutil.rmtree(d, ignore_errors=True)
