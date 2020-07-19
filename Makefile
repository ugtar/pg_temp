#!/usr/bin/env make

# External commands
CTAGS ?= ctags
FIND ?= find
PYTEST ?= py.test
PYTHON ?= python3
RM ?= rm -f
RM_R ?= rm -fr
SH ?= sh
TOX ?= tox

# Options
flags ?=

TESTCMD ?= $(PYTHON) -m pytest $(flags)
TOXCMD ?= $(TOX) --develop --skip-missing-interpreters

ifdef V
    TESTCMD += --verbose
    TOXCMD += --verbose
endif

INSTALL_ARGS =

ifndef mac_pkg
    ifdef prefix
        INSTALL_ARGS += --prefix=$(prefix)
    endif
endif

ifdef DESTDIR
    INSTALL_ARGS += --root=$(DESTDIR)
endif

# Data
ARTIFACTS := build
ARTIFACTS += dist
ARTIFACTS += tags
ARTIFACTS += *.egg-info

all:: help

help:
	@echo "================"
	@echo "Makefile Targets"
	@echo "================"
	@echo "make help - print this message"
	@echo "make test - run unit tests"
	@echo "make tox - run unit tests using multiple pythons via tox"
	@echo "make check - run style / lint checks"
	@echo "make clean - remove cruft"
	@echo "make install - install modules"
.PHONY: help

check:
	$(TOXCMD) -v -e flake8 $(flags)
.PHONY: check

clean:
	$(RM) *.py[cod]
	$(RM_R) __pycache__
	$(RM_R) $(ARTIFACTS)
.PHONY: clean

install:
	$(PYTHON) setup.py install $(INSTALL_ARGS)
.PHONY: install

tags:
	$(CTAGS) -f tags *.py

test:
	$(TESTCMD) tests/psycopg2_test.py
.PHONY: test

tox:
	$(TOXCMD) $(flags)
.PHONY: tox
