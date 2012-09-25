"""
ZYNC Python Library

A module for interacting with ZYNC.
"""

import json
import httplib
import httplib2
import platform
from urllib import urlencode
import os

class ZyncAuthenticationError(Exception):
    pass

class ZyncError(Exception):
    pass

config_path = os.path.dirname(__file__)
if config_path != "":
    config_path += "/"
config_path += "config.py"
#config_path = "%s/config.py" % ( os.path.dirname(__file__), )
if not os.path.exists( config_path ):
    raise ZyncError( "Could not locate config.py, please create." )
from config import *

required_config = [ "ZYNC_URL" ]

for key in required_config:
    if not key in globals():
        raise Exception( "config.py must define a value for %s." % ( key, ) )

dummy = httplib2.Http()
dummy.request( ZYNC_URL )

def get_config( var=None ):
    http = httplib2.Http()
    url = "%s/lib/get_config_api.php" % ( ZYNC_URL, )
    if var == None:
        resp, content = http.request( url, 'GET' )
        try:
            return json.loads(content)
        except ValueError:
            raise ZyncError( content )
    else:
        url += "?var=%s" % ( var, )
        resp, content = http.request( url, 'GET' )
        return content

CONFIG = get_config()
SERVER_PATHS = [ CONFIG["WIN_ROOT"], CONFIG["MAC_ROOT"] ]

def get_instance_types():
    http = httplib2.Http()
    resp, content = http.request( "%s/lib/get_instance_types.php" % ( ZYNC_URL, ), 'GET' )
    response_obj = json.loads(content)
    if response_obj["code"] == 1:
        raise Exception( "Could not retrieve list of instance types: %s" % ( response_obj["response"], ) )
    return response_obj["response"]

INSTANCE_TYPES = get_instance_types()

DEFAULT_INSTANCE_TYPE = '20x7'

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

def get_project_name( in_file ):
    """
    Takes the name of a file - either a Maya or Nuke script - and returns
    the name of the project it belongs to.
    """
    http = httplib2.Http()
    resp, content = http.request( "%s/lib/get_project_name.php?file=%s" % ( ZYNC_URL, in_file ), 'GET' )
    return json.loads(content)

def get_maya_output_path( in_file ):
    http = httplib2.Http()
    resp, content = http.request( "%s/lib/get_maya_output.php?file=%s" % ( ZYNC_URL, in_file ), 'GET' )
    return json.loads(content)

class HTTPBackend(object):
    """
    Methods for talking to services over http.
    """
    def __init__(self, username, password, timeout=2.0):
        """
        """
        self.url = ZYNC_URL
        self.http = httplib2.Http(timeout=timeout) 

        if self.up():
            self.cookie = self.__auth(username, password)
        else:
            raise ZyncError('ZYNC is down at URL: %s' % self.url)

    def up(self):
        """
        Ensures that Zync is up and running
        """
        try:
            data = self.http.request(self.url, 'GET')
        except httplib2.ServerNotFoundError:
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

    def __auth(self, username, password):
        """
        Authenticate with zync
        """
        url = '/'.join((self.url, 'validate.php'))
        data = urlencode({'user': username, 'pass': password})
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        resp, content = self.http.request(url, 'POST', data, headers=headers)

        return resp.get('set-cookie')

class Zync(HTTPBackend):
    """
    The entry point to the ZYNC service. Initialize this with your username
    and password.
    """
    def __init__(self, username, password, app='nuke', timeout=2.0):
        """
        Create a Zync object, for interacting with the ZYNC service
        """
        super(Zync, self).__init__(username, password, timeout)

        self.app = app.lower()

        JobSelect = NukeJob if self.app == 'nuke' else MayaJob
        self.job = JobSelect(self.cookie, self.url)

        self.path_mappings = []

    def add_path_mapping(self, from_path, to_replace):
        """
        Adds a path mapping that will be executed when a job is submitted.
        """
        self.path_mappings.append((from_path, to_replace))

    def add_path_mappings(self, mappings):
        """
        Adds multiple path mappings in the form of two-tuples:
                [ (from_path, to_path), ... ]
        """
        for from_path, to_path in mappings:
            self.add_path_mapping(from_path, to_path)

    def apply_mapping(self, input):
        """
        Cycles through all of the registered `self.path_mapping` items and
        applies them to the input.
        """
        for from_path, to_path in self.path_mappings:
            input = input.replace(from_path, to_path)

        return input

    def list(self, max=100, app=None):
        """
        Returns a list of all of the jobs on Zync
        """
        url  = '/'.join((self.url, 'lib', 'get_jobs.php'))
        params = dict(max=max)
        url = '?'.join((url, urlencode(params)))
        resp, content = self.http.request(url, 'GET')

        return load_json(content)


    def submit(self, *args, **kwargs):
        """
        Wraps the submit method for the initialized job object.
        See the documentation for `NukeJob.submit()` and `MayaJob.submit()`
        """
        file_params = kwargs.get('params', ())
        if file_params:
            for k in file_params:
                try:
                    file_params[k] = self.apply_mapping(file_params[k])
                except AttributeError:
                    continue
            kwargs['params'] = file_params

        return self.job.submit(*args, **kwargs)

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
        self.http = httplib2.Http()

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
        url = '/'.join((self.url, 'lib', 'submit_job.php'))
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        submit_params = {}
        submit_params['instance_type'] = DEFAULT_INSTANCE_TYPE
        submit_params['upload_only'] = 0
        submit_params['start_new_instances'] = 1
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
        if content:
            info = '\n'.join([content, params])
            raise ZyncError(info)
        else:
            return resp, content

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

	#for path in SERVER_PATHS:
	#	if script_path.find( path ) != -1:
	#		script_path = script_path.split( path )[-1]

	#if script_path.startswith(CONFIG["BROWSE_DIR"]):
	#	script_path = script_path[len(CONFIG["BROWSE_DIR"]):]
	
        submit_params = {}
        submit_params['job_type'] = 'Nuke'
        submit_params['write_node'] = write_name

	#script_split = script_path.split("/")

	#submit_params['file'] = "%s%s%s" % ( CONFIG["FILE_ROOT"], CONFIG["BROWSE_DIR"], script_path )
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


