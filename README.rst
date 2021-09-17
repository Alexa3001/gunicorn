Gunicorn
--------

.. image:: https://img.shields.io/pypi/v/gunicorn.svg?style=flat
    :alt: PyPI version
    :target: https://pypi.python.org/pypi/gunicorn

.. image:: https://img.shields.io/pypi/pyversions/gunicorn.svg
    :alt: Supported Python versions
    :target: https://pypi.python.org/pypi/gunicorn

.. image:: https://travis-ci.org/benoitc/gunicorn.svg?branch=master
    :alt: Build Status
    :target: https://travis-ci.org/benoitc/gunicorn

This is a fork of the Gunicorn package, in which more options were added to manage the worker processes more efficiently and to obtain useful telemetry.

Gunicorn 'Green Unicorn' is a Python WSGI HTTP Server for UNIX. It's a pre-fork
worker model ported from Ruby's Unicorn_ project. The Gunicorn server is broadly
compatible with various web frameworks, simply implemented, light on server
resource usage, and fairly speedy.

Documentation
-------------

The main documentation is hosted at https://docs.gunicorn.org.

The following options were added to control worker restarts:

*--wait-for-new-workers:* if set, a worker does not terminate immediately after it reached the planned number of requests; instead, it waits until a new worker is ready to replace it

*--max-restarting-workers:* enforces an upperbound for the number of workers which can be restarted simultaneously; the default is 0, which means that there is no upperbound; works only when --wait-for-new-workers is set

*--warmup-requests:* number of requests a new worker needs to handle until it is considered to be ready, so that the old worker can terminate; 0 by default


The following option was added to provide some telemetry:

*--enrich-response:* if set, extra information is added to the response body (such as timestamps and worker pid)

Installation
------------

Gunicorn requires **Python 3.x >= 3.5**.

::

    $ git clone <repo-url>
    $ pip install -e gunicorn

Usage
-----

Basic usage::

    $ gunicorn [OPTIONS] APP_MODULE

Where ``APP_MODULE`` is of the pattern ``$(MODULE_NAME):$(VARIABLE_NAME)``. The
module name can be a full dotted path. The variable name refers to a WSGI
callable that should be found in the specified module.

Example with test app::

    $ cd examples
    $ gunicorn --workers=2 test:app --max-requests=100 --max-requests-jitter=30 --log-level=debug --wait-for-new-workers --enrich-response --max-restarting-workers=1  --warmup-requests=2






.. _Unicorn: https://bogomips.org/unicorn/
.. _`#gunicorn`: https://webchat.freenode.net/?channels=gunicorn
.. _Freenode: https://freenode.net/
.. _LICENSE: https://github.com/benoitc/gunicorn/blob/master/LICENSE
