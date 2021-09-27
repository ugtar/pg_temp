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
import shlex
import warnings


# Module level TempDB singleton
temp_db = None


# Module constants
DEFAULT_DOCKER_EXE = 'docker'
DOCKER_INTERNAL_SOCK_DIR = '/var/run/postgresql'
FALLBACK_DOCKER_IMG = 'postgres'

DEFAULT_POSTGRES = 'postgres'
DEFAULT_INITDB = 'initdb'
DEFAULT_PSQL = 'psql'
DEFAULT_CREATEUSER = 'createuser'


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


class PGSetupError(Exception):
    pass


class TempDB(object):
    def __init__(
        self,
        databases=None,
        verbosity=1,
        retry=5,
        tincr=1.0,
        docker_img=None,
        initdb=DEFAULT_INITDB,
        postgres=DEFAULT_POSTGRES,
        psql=DEFAULT_PSQL,
        createuser=DEFAULT_CREATEUSER,
        dirname=None,
        sock_dir=None,
        options=None,
    ):
        """Initialize a temporary Postgres database

        :param databases: list of databases to create
        :param verbosity: verbosity level, larger values are more verbose
        :param retry: number of times to retry a connection
        :param tincr: how much time to wait between retries
        :param docker_img: specify a docker image for postgres
        :param initdb: path to `initdb`, defaults to first in $PATH
        :param postgres: path to `postgres`, defaults to first in $PATH
        :param psql: path to `psql`, defaults to first in $PATH
        :param createuser: path to `createuser`, defaults to first in $PATH
        :param dirname: override temp data directory generation and create the
            db in `dirname`
        :param sock_dir: specify the postgres socket directory
        :param options: a dictionary of configuration params and values
            passed to `postgres` with `-c`

        """
        self.verbosity = verbosity
        self.docker_prefix = None
        self.docker_container = None
        self.docker_img = docker_img
        # check for a postgres install, or fallback to docker
        self._get_docker_fallback(postgres)
        self.pg_process = None
        # we won't expose this yet
        self.run_as = self._get_run_as_account(None)
        self.current_user = pwd.getpwuid(os.geteuid()).pw_name
        options = dict() if not options else options
        self._setup(
            databases,
            retry,
            tincr,
            initdb,
            postgres,
            sock_dir,
            psql,
            createuser,
            dirname,
            options,
        )

    def _get_docker_fallback(self, postgres_exe):
        if self.docker_img:
            # already using docker
            return
        if postgres_exe != DEFAULT_POSTGRES:
            # exe was specified explicitly so don't use a fallback
            return
        if not shutil.which(DEFAULT_POSTGRES):
            has_docker = shutil.which(DEFAULT_DOCKER_EXE)
            if not has_docker:
                raise PGSetupError("Unable to locate a postgres installation")
            warnings.warn(
                "Unable to locate a postgres install. "
                "Attempting fallback to docker..."
            )
            self.docker_img = FALLBACK_DOCKER_IMG

    def _setup_docker_prefix(self, *args, mode='init'):
        if mode == 'init':
            self.docker_prefix = [
                DEFAULT_DOCKER_EXE,
                'run',
                '--rm',
                '-e',
                'POSTGRES_HOST_AUTH_METHOD=trust',
                '--user=postgres',
            ]
        elif mode == 'exec':
            self.docker_prefix = [DEFAULT_DOCKER_EXE, 'exec', '--user=postgres', *args]

    def _get_run_as_account(self, run_as):
        if run_as:
            try:
                return pwd.getpwnam(run_as)
            except KeyError:
                raise PGSetupError(
                    "Can't locate user {}!".format(
                        run_as,
                    )
                )
        current_euid = os.geteuid()
        if current_euid == 0:
            # If running as root, try to run the db server creation as postgres
            # user (assumed to exist)
            try:
                return pwd.getpwnam('postgres')
            except KeyError:
                raise PGSetupError(
                    "Can't create DB server as root, and " "there's no postgres user!"
                )
        return None

    @contextmanager
    def _do_run_as(self):
        if not self.run_as:
            yield
            return
        current_euid = os.geteuid()
        current_egid = os.getegid()
        try:
            os.setegid(self.run_as.pw_gid)
            os.seteuid(self.run_as.pw_uid)
            yield
        finally:
            os.seteuid(current_euid)
            os.setegid(current_egid)

    def _user_subshell(self, cmd):
        # Note: we can't just seteuid because the postgres server process
        # checks that euid == uid and that euid is not 0
        # http://doxygen.postgresql.org/main_8c.html#a0bd2ee2e17615192912a97c16f908ac2
        # and, if we set both uid and euid to non-zero, we won't be able to
        # switch back. Instead we must run in a child process with both uid and
        # euid set -- hence, `su`.
        if not self.run_as:
            return cmd
        return ['su', '-', 'postgres', '-c', ' '.join(shlex.quote(c) for c in cmd)]

    def stdout(self, level):
        """Return file handle for stdout for the current verbosity"""
        if level > self.verbosity:
            return subprocess.DEVNULL
        else:
            return sys.stdout

    def stderr(self, level):
        """Return file handle for stderr for the current verbosity"""
        if level > self.verbosity:
            return subprocess.DEVNULL
        else:
            return sys.stderr

    def printf(self, msg, level=1):
        if level > self.verbosity:
            return
        print(msg)

    def run_cmd(self, cmd, level=0, bg=False):
        if self.docker_prefix:
            cmd = self.docker_prefix + cmd
        else:
            cmd = self._user_subshell(cmd)
        self.printf("Running %s" % str(' '.join(cmd)))
        p = subprocess.Popen(cmd, stdout=self.stdout(level), stderr=self.stderr(level))
        if bg:
            return p
        p.communicate()
        return p.returncode == 0

    def _setup(
        self,
        databases,
        retry,
        tincr,
        initdb,
        postgres,
        sock_dir,
        psql,
        createuser,
        dirname,
        options,
    ):

        databases = databases or []
        try:
            self.printf("Creating temp PG server...")
            with self._do_run_as():
                self._setup_directories(dirname, sock_dir)
            if self.docker_img:
                self._setup_docker_prefix(mode='init')
            self.create_db_server(initdb, postgres, options)
            if self.docker_img:
                self._setup_docker_prefix(self.docker_container, mode='exec')
                self._real_pg_socket_dir = self.pg_socket_dir
                self.pg_socket_dir = DOCKER_INTERNAL_SOCK_DIR
            self.test_connection(psql, retry, tincr)
            self.create_user(createuser)
            self.create_databases(psql, databases)
            if self.docker_img:
                self.pg_socket_dir = self._real_pg_socket_dir
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
            # this is mainly needed in the case of docker so that that docker
            # image's internal posgres user has write access to the socket dir
            os.chmod(self.pg_socket_dir, 0o777)
        else:
            self.pg_socket_dir = sock_dir

    def create_db_server(self, initdb, postgres, options):
        if not self.docker_prefix:
            rc = self.run_cmd([initdb, self.pg_data_dir], level=2)
            if not rc:
                raise PGSetupError("Couldn't initialize temp PG data dir")
        options = ['%s=%s' % (k, v) for (k, v) in options.items()]
        if self.docker_prefix:
            _, cidfile = tempfile.mkstemp()
            os.unlink(cidfile)
            cmd = [
                '-d',
                '--cidfile',
                cidfile,
                '-v',
                self.pg_socket_dir + ':' + DOCKER_INTERNAL_SOCK_DIR,
                self.docker_img,
                postgres,
                '-F',
                '-T',
                '-h',
                '',
            ]
            bg = False
        else:
            cmd = [
                postgres,
                '-F',
                '-T',
                '-D',
                self.pg_data_dir,
                '-k',
                self.pg_socket_dir,
                '-h',
                '',
            ]
            bg = True
        cmd += flatten(zip(itertools.repeat('-c'), options))

        self.pg_process = self.run_cmd(cmd, level=2, bg=bg)
        if self.docker_prefix:
            with open(cidfile) as f:
                self.docker_container = f.read()
            os.unlink(cidfile)

    def test_connection(self, psql, retry, tincr):
        # test connection
        cmd = [psql, '-d', 'postgres', '-h', self.pg_socket_dir, '-c', r"\dt"]
        for i in range(retry):
            time.sleep(tincr)
            rc = self.run_cmd(cmd, level=2)
            if rc:
                break
        else:
            raise PGSetupError("Couldn't start PG server")
        return rc

    def create_user(self, createuser):
        cmd = [createuser, '-h', self.pg_socket_dir, self.current_user, '-s']
        rc = self.run_cmd(cmd, level=2)
        if not rc:
            # maybe the user already exists, and that's ok
            pass
        return rc

    def create_databases(self, psql, databases):
        rc = True
        for db in databases:
            cmd = [
                psql,
                '-d',
                'postgres',
                '-h',
                self.pg_socket_dir,
                '-c',
                "create database %s;" % db,
            ]
            rc = rc and self.run_cmd(cmd, level=2)
        if not rc:
            raise PGSetupError("Couldn't create databases")
        return rc

    def cleanup(self):
        if self.docker_container:
            subprocess.run(
                [DEFAULT_DOCKER_EXE, 'kill', self.docker_container],
                stdout=subprocess.DEVNULL,
            )
        elif self.pg_process:
            self.pg_process.kill()
            self.pg_process.wait()
        for d in [self.pg_temp_dir]:
            if d:
                shutil.rmtree(d, ignore_errors=True)
