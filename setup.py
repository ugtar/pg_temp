#!/usr/bin/env python

import os

try:
    import setuptools as setup_mod
except ImportError:
    import distutils.core as setup_mod

here = os.path.dirname(__file__)
version = os.path.join(here, 'pg_temp', 'version.py')
scope = {}
exec(open(version).read(), scope)


with open("README.md", "r") as fh:
    long_description = fh.read()


SETUP_ARGS = dict(
    name='pg_temp',
    version=scope['__version__'],
    description='Quickly create Postgres databases, e.g. for testing',
    long_description=long_description,
    long_description_content_type="text/markdown",
    author='Uri Okrent',
    author_email='uokrent@gmail.com',
    url='https://github.com/ugtar/pg_temp',
    license='MIT',
    platforms=['POSIX'],
    keywords=['postgres', 'testing'],
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
    ],
    options={'clean': {'all': 1}},
    packages=['pg_temp'],
    python_requires='>=3.5',
)


if __name__ == '__main__':
    setup_mod.setup(**SETUP_ARGS)
