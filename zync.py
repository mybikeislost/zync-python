"""
ZYNC Python Library

A module for interacting with ZYNC.
"""

import json
import zync_lib.httplib2
import platform
from urllib import urlencode
import os

class ZyncAuthenticationError(Exception):
    pass

class ZyncError(Exception):
    pass

config_path = os.path.dirname(__file__)
if config_path != '':
    config_path += '/'
config_path += 'config.py'
if not os.path.exists(config_path):
    raise ZyncError('Could not locate config.py, please create.')
from config import *

required_config = ['ZYNC_URL']

for key in required_config:
    if not key in globals():
        raise Exception('config.py must define a value for %s.' % (key,))

DEFAULT_INSTANCE_TYPE = 'ZYNC20'

VRAY_RENDERER = 'vray'
SOFTWARE_RENDERER = 'sw'
MENTAL_RAY_RENDERER = 'mr'
MAYA_DEFAULT_RENDERER = 'vray'
MAYA_RENDERERS = {
                    SOFTWARE_RENDERER: 'Maya Software',
                    VRAY_RENDERER: 'V-Ray',
                    MENTAL_RAY_RENDERER: 'Mental Ray'
                 }

def load_json(content):
    """
    Load JSON from ZYNC, taking care to strip characters that the json module 
    can't parse correctly.
    """
    # get_jobs.php doesn't return standard parseable JSON, so strip out the
    # open/close parens
    if content.startswith('(') and content.endswith(')'):
        content = content.strip('(')
        content = content.strip(')')

    return json.loads(content)

class HTTPBackend(object):
    """
    Methods for talking to services over http.
    """
    def __init__(self, script_name, token, timeout=2.0):
        """
        """
        self.url = ZYNC_URL
        self.http = zync_lib.httplib2.Http(timeout=timeout) 
        self.script_name = script_name
        self.token = token
        if self.up():
            self.cookie = self.__auth(self.script_name, self.token)
        else:
            raise ZyncError('ZYNC is down at URL: %s' % self.url)

    def login(self, username=None, password=None):
        if self.up():
            self.cookie = self.__auth(self.script_name, self.token, username=username, password=password)
        else:
            raise ZyncError('ZYNC is down at URL: %s' % self.url)

    def up(self):
        """
        Ensures that Zync is up and running
        """
        try:
            data = self.http.request(self.url, 'GET')
        except zync_lib.httplib2.ServerNotFoundError:
            return False
        except AttributeError:
            # trying to make a socket failes sometimes when connecting
            return False
        else:
            status = data[0].get('status', '404')
            return status.startswith('2') or status.startswith('3')

    def status(self):
        """
        Checks the server status
        """
        if self.up():
            url = '/'.join((self.url, 'lib', 'check_server.php'))
            resp, status = self.http.request(url, 'GET')
            return status
        else:
            return 'down'

    def set_cookie(self, headers={}):
        """
        Adds the auth cookie to the given headers, raises
        ZyncAuthenticationError if cookie doesn't exist
        """
        if self.cookie:
            headers['Cookie'] = self.cookie
            return headers
        else:
            raise ZyncAuthenticationError('ZYNC Auth Failed')

    def __auth(self, script_name, token, username=None, password=None):
        """
        Authenticate with zync
        """
        url = '/'.join((self.url, 'validate.php'))
        args = { 'script_name': script_name, 'token': token }
        if username != None:
            args['user'] = username
            args['pass'] = password
        data = urlencode(args)
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        resp, content = self.http.request(url, 'POST', data, headers=headers)
        response_obj = json.loads( content )
        if response_obj["code"] == 0:
            return resp.get('set-cookie')
        else:
            raise ZyncAuthenticationError( response_obj["response"] )

class Zync(HTTPBackend):
    """
    The entry point to the ZYNC service. Initialize this with your username
    and password.
    """
    def __init__(self, script_name, token, timeout=2.0):
        """
        Create a Zync object, for interacting with the ZYNC service
        """
        super(Zync, self).__init__(script_name, token, timeout=timeout)

        self.CONFIG = self.get_config()
        self.INSTANCE_TYPES = self.get_instance_types()
        self.FEATURES = self.get_enabled_features()

    def list(self, max=100, app=None):
        """
        Returns a list of all of the jobs on Zync
        """
        url  = '/'.join((ZYNC_URL, 'lib', 'get_jobs.php'))
        params = dict(max=max)
        url = '?'.join((url, urlencode(params)))
        resp, content = self.http.request(url, 'GET', headers=headers) 

        return load_json(content)

    def get_project_name(self, in_file):
        """
        Takes the name of a file - either a Maya or Nuke script - and returns
        the name of the project it belongs to.
        """
        url = '%s/lib/get_project_name.php?file=%s' % (ZYNC_URL, in_file)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        return load_json(content)

    def get_maya_output_path(self, in_file):
        url = '%s/lib/get_maya_output.php?file=%s' % (ZYNC_URL, in_file)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        return load_json(content)

    def get_config(self, var=None):
        url = '%s/lib/get_config_api.php' % (ZYNC_URL,)
        headers = self.set_cookie()
        if var == None:
            resp, content = self.http.request(url, 'GET', headers=headers)
            try:
                return load_json(content)
            except ValueError:
                raise ZyncError(content)
        else:
            url += '?var=%s' % (var,)
            resp, content = self.http.request(url, 'GET', headers=headers)
            return content

    def get_instance_types(self):
        url = '%s/lib/get_instance_types.php' % (ZYNC_URL,)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        response_obj = load_json(content)
        if response_obj['code'] == 1:
            raise ZyncError('Could not retrieve list of instance types: %s' % (response_obj["response"],))
        return response_obj['response']

    def get_enabled_features(self):
        url = '%s/lib/get_enabled_features.php' % (ZYNC_URL,)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        response_obj = load_json(content)
        if response_obj['code'] == 1:
            raise ZyncError('Could not retrieve list of enabled features: %s' % (response_obj["response"],))
        return response_obj['response']

    def get_job_params(self, jobid):
        url = '%s/lib/get_job_params.php?job_id=%d' % (ZYNC_URL,jobid,)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        return content

    def submit_job(self, job_type, *args, **kwargs):
        job_type = job_type.lower()

        JobSelect = NukeJob if job_type == 'nuke' else MayaJob
        self.job = JobSelect(self.cookie, self.url)

        return self.job.submit(*args, **kwargs)

    def submit(self, *args, **kwargs):
        """
        Wraps the submit method for the initialized job object.
        See the documentation for `NukeJob.submit()` and `MayaJob.submit()`
        """
        return self.job.submit(*args, **kwargs)

    def get_triggers(self, user=None, show_seen=False):
        """
        Returns a list of current trigger events in ZYNC
        """
        url  = '/'.join((self.url, 'lib', 'get_triggers.php'))
        params = {}
        if show_seen == True:
            params["show_seen"] = 1
        else:
            params["show_seen"] = 0
        if user != None:
            params["user"] = user
        url = '?'.join((url, urlencode(params)))
        resp, content = self.http.request(url, 'GET')

        return json.loads(content)

class Job(object):
    """
    Zync Job class
    """
    def __init__(self, cookie, url):
        """
        The base Zync Job object, not useful on its own, but should be
        the parent for app specific Job implementations.
        """
        if cookie:
            self.cookie = cookie
        else:
            raise ZyncAuthenticationError('ZYNC Auth Failed')

        self.url = url
        self.http = zync_lib.httplib2.Http()

    def set_cookie(self, headers, cookie=None):
        """
        Adds the auth cookie to the given headers, raises
        ZyncAuthenticationError if cookie doesn't exist
        """
        if cookie:
            self.cookie = cookie

        if self.cookie:
            headers['Cookie'] = self.cookie
            return headers
        else:
            raise ZyncAuthenticationError('ZYNC Auth Failed')

    def cancel(self, job_id):
        """
        Cancels the given job.

        Sets the status of job_id to 'canceled'.
        """
        return self.set_status(job_id, 'canceled')

    def delete(self, job_id):
        """
        Deletes the given job.
        """

        url = '/'.join((self.url, 'lib', 'delete_job.php'))
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        headers = self.set_cookie(headers)

        params = {'job_id': job_id}
        resp, content = self.http.request(url, 'POST', urlencode(params),
                                          headers=headers)

        return resp, content

    def params(self, job_id):
        """
        Returns a dictionary of the job parameters
        """
        url = '/'.join((self.url, 'lib', 'get_job_params.php'))
        data = urlencode({'job_id': job_id})
        url = '?'.join((url, data))
        resp, content = self.http.request(url, 'GET')

        return load_json(content)

    def pause(self, job_id):
        """
        Pauses the given job.

        Sets the status of job_id to 'paused'.
        """
        return self.set_status(job_id, 'paused')

    def retry(self, job_id):
        """
        Retries the errored tasks for the given job ID.
        """
        url = '/'.join((self.url, 'lib', 'retry_errors.php'))
        data = urlencode({'job_id': job_id})
        url = '?'.join((url, data))

        return self.http.request(url, 'GET')

    def restart(self, job_id):
        """
        Requeues the given job.

        Sets the status of job_id to 'queued'.
        """
        return self.set_status(job_id, 'queued')

    def set_status(self, job_id, status):
        """
        Sets the job status for the given job
        """
        url = '/'.join((self.url, 'lib', 'set_job_status.php'))
        data = urlencode(dict(job_id=job_id, status=status))
        url = '?'.join((url, data))

        return self.http.request(url, 'GET')

    def submit(self, params):
        """
        Submit a job to Zync
        """
        url = '/'.join((self.url, 'lib', 'submit_job_v2.php'))
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        submit_params = {}
        submit_params['instance_type'] = DEFAULT_INSTANCE_TYPE
        submit_params['upload_only'] = 0
        submit_params['start_new_slots'] = 1
        submit_params['chunk_size'] = 1
        submit_params['distributed'] = 0
        submit_params['num_instances'] = 1
        submit_params['skip_check'] = 0
        submit_params['notify_complete'] = 0

        submit_params.update(params)

        if 'scene_info' in submit_params:
            submit_params['scene_info'] = json.dumps(submit_params['scene_info'])
            print submit_params['scene_info']

        headers = self.set_cookie(headers)

        resp, content = self.http.request(url, 'POST', urlencode(submit_params),
                                          headers=headers)

        # if submit_job.php fails, a failure string will be returned,
        # we want to raise that so that users can deal with it
        # (if it works, nothing will be returned)
        response_obj = load_json(content)
        if response_obj['code'] == 1:
            raise ZyncError('Could not submit job: %s' % (response_obj["response"],))
        return response_obj['response']
 
    def unpause(self, job_id):
        """
        Unpauses the given job ID.

        Sets the status of job_id to 'running'
        """
        return self.set_status(job_id, 'running')

class NukeJob(Job):
    """
    Encapsulates Nuke-specific Job functions
    """
    def __init__(self, *args):
        super(NukeJob, self).__init__(*args)

    def submit(self, script_path, write_name, params=None):
        """
        Submits a Nuke Job to ZYNC.

        Nuke-specific submit parameters:
            write_node: The write node to render. Can be 'All' to render
                        all nodes.
        """
        #script_path = os.path.realpath(script_path)

        submit_params = {}
        submit_params['job_type'] = 'Nuke'
        submit_params['write_node'] = write_name

	submit_params['file'] = script_path 

        if params:
            submit_params.update(params)

        return super(NukeJob, self).submit(submit_params)

class MayaJob(Job):
    """
    Encapsulates Maya-specific job functions
    """
    def __init__(self, *args):
        super(MayaJob, self).__init__(*args)

    def submit(self, file, layers, params=None):
        """
        Maya-specific submit parameters:
            project: Maya project directory
            out_path: output render path
            renderer: the renderer to use. See 'Available Renderers'
            camera: the name of the camera
            layers: a list of layer names to render.
                    WARNING: must be a comma separated string, like:
                             'renderLayer1,renderLayer2,renderLayer3'

            xres: image x-resolution
            yres: image y-resolution

            distributed: (V-Ray only) Turns on distributed rendering

        Available Renderers:
            'sw' : Maya Software
            'vray': V-Ray
            'mr': Mental Ray
        """
        #file = os.path.realpath(file)

        submit_params = {}
        submit_params['job_type'] = 'Maya'
        submit_params['file'] = file

        submit_params['layers'] = layers

        if params:
            submit_params.update(params)

        return super(MayaJob, self).submit(submit_params)


