"""How the app is served in production.

The dev server is a single process that reloads itself. Gunicorn is several
processes that do not, and nearly everything below exists because of that
difference.
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Two workers, not `2 * cpus + 1`.
#
# The usual formula sizes for CPU-bound work on a machine that has nothing else
# to do. This app is I/O-bound against a SQLite file on the same disk, serving
# 2-5 people, on an instance with 1 GB of RAM that is also running a reverse
# proxy. Each worker holds its own copy of the food and exercise libraries, so
# the cost of an extra one is real and the benefit is nil.
#
# Two rather than one so a slow request does not block everyone, and so a worker
# that dies has a colleague to cover the gap while it restarts.
workers = int(os.environ.get('WEB_CONCURRENCY', 2))

# Threads within each worker, because the work is waiting on SQLite rather than
# burning CPU. Every request opens its own connection, so there is no shared
# handle to serialise on.
threads = int(os.environ.get('WEB_THREADS', 4))
worker_class = 'gthread'

# Load the application *before* forking, which is not an optimisation here - it
# is a correctness fix.
#
# app.py runs init_db() at import, so without preload each of the two workers
# would import the module and race the other to apply migrations to the same
# SQLite file. Preloading imports once, in the master, and forks workers that
# inherit the result. The memory saving is a bonus.
preload_app = True

# 30s: long enough for the slowest honest request (the Excel export walks every
# table), short enough that a wedged worker is recycled rather than sat on.
timeout = 30
graceful_timeout = 30

# Recycle workers periodically. SQLite connections, the food library cache and
# anything else that accumulates get a clean slate, and a slow leak never gets
# the chance to become an outage. The jitter stops both workers restarting in
# the same second.
max_requests = 1000
max_requests_jitter = 100

# stdout/stderr, because the container's logs are the log. Writing to a file
# inside a container is writing to a layer nobody will read.
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('LOG_LEVEL', 'info')

# The client address as the proxy reported it, not the proxy's own. Pairs with
# the ProxyFix in security.py - without both, every line of the access log says
# the request came from Caddy.
forwarded_allow_ips = '*'
access_log_format = '%({x-forwarded-for}i)s %(m)s %(U)s %(s)s %(L)ss'
