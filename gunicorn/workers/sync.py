# -*- coding: utf-8 -
#
# This file is part of gunicorn released under the MIT license.
# See the NOTICE for more information.
#

import datetime as dt
from itertools import chain
import errno
import os
import select
import socket
import ssl
import sys

import json
import gunicorn.http as http
import gunicorn.http.wsgi as wsgi
import gunicorn.util as util
import gunicorn.workers.base as base


class StopWaiting(Exception):
    """ exception raised to stop waiting for a connection """


class SyncWorker(base.Worker):

    def accept(self, listener):
        client, addr = listener.accept()
        client.setblocking(1)
        util.close_on_exec(client)
        self.handle(listener, client, addr)

    def wait(self, timeout):
        try:
            self.notify()
            ret = select.select(self.wait_fds, [], [], timeout)
            if ret[0]:
                if self.PIPE[0] in ret[0]:
                    os.read(self.PIPE[0], 1)
                return ret[0]

        except select.error as e:
            if e.args[0] == errno.EINTR:
                return self.sockets
            if e.args[0] == errno.EBADF:
                if self.nr < 0:
                    return self.sockets
                else:
                    raise StopWaiting
            raise

    def is_parent_alive(self):
        # If our parent changed then we shut down.
        if self.ppid != os.getppid():
            self.log.info("Parent changed, shutting down: %s", self)
            return False
        return True

    def run_for_one(self, timeout):
        listener = self.sockets[0]
        while self.alive:
            self.notify()

            # Accept a connection. If we get an error telling us
            # that no connection is waiting we fall down to the
            # select which is where we'll wait for a bit for new
            # workers to come give us some love.
            try:
                self.accept(listener)
                # Keep processing clients until no one is waiting. This
                # prevents the need to select() for every client that we
                # process.
                continue

            except EnvironmentError as e:
                if e.errno not in (errno.EAGAIN, errno.ECONNABORTED,
                                   errno.EWOULDBLOCK):
                    raise

            if not self.is_parent_alive():
                return

            try:
                self.wait(timeout)
            except StopWaiting:
                return

    def run_for_multiple(self, timeout):
        while self.alive:
            self.notify()

            try:
                ready = self.wait(timeout)
            except StopWaiting:
                return

            if ready is not None:
                for listener in ready:
                    if listener == self.PIPE[0]:
                        continue

                    try:
                        self.accept(listener)
                    except EnvironmentError as e:
                        if e.errno not in (errno.EAGAIN, errno.ECONNABORTED,
                                           errno.EWOULDBLOCK):
                            raise

            if not self.is_parent_alive():
                return

    def run(self, is_new): ###
        ### Notify master that this worker is ready
        if is_new and self.wait_for_new_workers:
            self.call_when_ready(self.pid)


        # if no timeout is given the worker will never wait and will
        # use the CPU for nothing. This minimal timeout prevent it.
        timeout = self.timeout or 0.5

        # self.socket appears to lose its blocking status after
        # we fork in the arbiter. Reset it here.
        for s in self.sockets:
            s.setblocking(0)

        if len(self.sockets) > 1:
            self.run_for_multiple(timeout)
        else:
            self.run_for_one(timeout)

    def handle(self, listener, client, addr):
        req = None
        try:
            if self.cfg.is_ssl:
                client = ssl.wrap_socket(client, server_side=True,
                                         **self.cfg.ssl_options)

            parser = http.RequestParser(self.cfg, client, addr)
            req = next(parser)
            self.handle_request(listener, req, client, addr)
        except http.errors.NoMoreData as e:
            self.log.debug("Ignored premature client disconnection. %s", e)
        except StopIteration as e:
            self.log.debug("Closing connection. %s", e)
        except ssl.SSLError as e:
            if e.args[0] == ssl.SSL_ERROR_EOF:
                self.log.debug("ssl connection closed")
                client.close()
            else:
                self.log.debug("Error processing SSL request.")
                self.handle_error(req, client, addr, e)
        except EnvironmentError as e:
            if e.errno not in (errno.EPIPE, errno.ECONNRESET, errno.ENOTCONN):
                self.log.exception("Socket error processing request.")
            else:
                if e.errno == errno.ECONNRESET:
                    self.log.debug("Ignoring connection reset")
                elif e.errno == errno.ENOTCONN:
                    self.log.debug("Ignoring socket not connected")
                else:
                    self.log.debug("Ignoring EPIPE")
        except Exception as e:
            self.handle_error(req, client, addr, e)
        finally:
            util.close(client)

    def handle_request(self, listener, req, client, addr):
        # time 1
        time1_raw = dt.datetime.utcnow()
        time1 = int((time1_raw - dt.datetime(1970,1,1)).total_seconds() * 1e6)

        environ = {}
        resp = None
        try:
            self.cfg.pre_request(self, req)

            resp, environ = wsgi.create(req, client, addr,
                                        listener.getsockname(), self.cfg)
            # Force the connection closed until someone shows
            # a buffering proxy that supports Keep-Alive to
            # the backend.
            resp.force_close()

            self.nr += 1

            if self.nr == self.max_requests:
                if self.wait_for_new_workers: # use the pipe to announce that you reached the planned number of requests
                    self.log.info("Worker %s tells master to restart it.", self.pid)
                    self.call_when_tired(self.pid)
                else: # autorestart immediately
                    self.log.info("Autorestarting worker after current request.")
                    self.alive = False

            # time 2
            time2_raw = dt.datetime.utcnow()
            time2 = int((time2_raw - dt.datetime(1970, 1, 1)).total_seconds() * 1e6)

            respiter1 = self.wsgi(environ, resp.start_response)

            # time 3
            time3_raw = dt.datetime.utcnow()
            time3 = int((time3_raw - dt.datetime(1970, 1, 1)).total_seconds() * 1e6)


            if self.enrich_response:
                info = json.dumps({ "t1": time1, "d1": time2 - time1, "d2": time3 - time2, "pid": self.pid, "nr": self.nr, "max": self.max_requests})
                info_bytes = info.encode()

                respiter = chain(iter(['{"res": '.encode()]), respiter1, iter([', "info": '.encode()]), iter([info_bytes]), iter(['}'.encode()])) # join iterators

                ### Modify Content-Length in both places
                resp.response_length += len(info_bytes) + 19

                for i in range(len(resp.headers)):
                    if(resp.headers[i][0] == 'Content-Length'):
                        resp.headers[i] = (resp.headers[i][0], str(resp.response_length))
            else:
                respiter = respiter1



            try:
                if isinstance(respiter, environ['wsgi.file_wrapper']):
                    resp.write_file(respiter)
                else:
                    for item in respiter:
                        resp.write(item)
                resp.close()


                self.log.access(resp, req, environ, time3_raw - time1_raw)
            finally:
                if hasattr(respiter, "close"):
                    respiter.close()
        except EnvironmentError:
            # pass to next try-except level
            util.reraise(*sys.exc_info())
        except Exception:
            if resp and resp.headers_sent:
                # If the requests have already been sent, we should close the
                # connection to indicate the error.
                self.log.exception("Error handling request")
                try:
                    client.shutdown(socket.SHUT_RDWR)
                    client.close()
                except EnvironmentError:
                    pass
                raise StopIteration()
            raise
        finally:
            try:
                self.cfg.post_request(self, req, environ, resp)
            except Exception:
                self.log.exception("Exception in post_request hook")
