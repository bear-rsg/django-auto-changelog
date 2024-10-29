# Middleware to get the current username (if there is one).

import os
import pwd
from threading import local

_thread_local = local()


def get_current_username():
    username = getattr(_thread_local, '_bkdb_username', None)
    if username is None:
        # Probably running in a script - get the username of the user running the script
        username = pwd.getpwuid(os.getuid()).pw_name
    return username


class CurrentUsernameMiddleware(object):
    def __init__(self, get_response):
        """
        One-time init of the middleware
        """
        self.get_response = get_response

    def __call__(self, request):
        """
        Temporarily store the username in our thread local storage, while the request is being processed
        """
        _thread_local._bkdb_username = request.user.username
        response = self.get_response(request)
        del _thread_local._bkdb_username
        return response
