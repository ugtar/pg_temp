#!/usr/bin/env python

import os
try:
    import setuptools as setup_mod
except ImportError:
    import distutils.core as setup_mod

here = os.path.dirname(__file__)
version = os.path.join(here, 'pg_temp.py')
scope = {}
exec(open(version).read(), scope)

SETUP_ARGS = dict(
    name='pg_temp',
    version=scope['__version__'],
    description='Quickly create Postgres databases, e.g. for testing',
    long_description='A library for creating temporary Postgres databases.',
    author='Uri Okrent',
    author_email='ugtar -at- gmail.com',
    url='https://github.com/ugtar/pg_temp',
    license='MIT',
    platforms=['POSIX'],
    keywords=['postgres', 'testing'],
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
    ],
    options={'clean': {'all': 1}},
    py_modules=['pg_temp'],
)


if __name__ == '__main__':
    setup_mod.setup(**SETUP_ARGS)
