"""
ZYNC Python Library

A module for interacting with ZYNC.
"""

import sys, os, json, platform
from urllib import urlencode
import zync_lib.httplib2

class ZyncAuthenticationError(Exception):
    pass

class ZyncError(Exception):
    pass

class ZyncConnectionError(Exception):
    pass

class ZyncPreflightError(Exception):
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

DEFAULT_INSTANCE_TYPE = 'ZYNC16'
MAYA_DEFAULT_RENDERER = 'vray'

def load_json(content):
    """
    Load JSON from ZYNC, taking care to strip characters that the json module 
    can't parse correctly.
    """
    # some API scripts don't return standard parseable JSON, so strip out the
    # open/close parens
    if content.startswith('(') and content.endswith(')'):
        content = content.strip('(')
        content = content.strip(')')

    return json.loads(content)

class HTTPBackend(object):
    """
    Methods for talking to services over http.
    """
    def __init__(self, script_name, token, timeout=10.0, validate=True):
        """
        """
        self.url = ZYNC_URL
        self.validate = validate
        if self.validate:
            self.http = zync_lib.httplib2.Http(timeout=timeout) 
        else:
            self.http = zync_lib.httplib2.Http(timeout=timeout, disable_ssl_certificate_validation=True) 
        self.script_name = script_name
        self.token = token
        if self.up():
            self.cookie = self.__auth(self.script_name, self.token)
        else:
            raise ZyncConnectionError('ZYNC is down at URL: %s' % self.url)

    def login(self, username=None, password=None):
        if self.up():
            self.cookie = self.__auth(self.script_name, self.token, username=username, password=password)
        else:
            raise ZyncConnectionError('ZYNC is down at URL: %s' % self.url)

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
            url = '%s/lib/check_server.php' % (self.url,)
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
            raise ZyncAuthenticationError('ZYNC Authentication failed.')

    def __auth(self, script_name, token, username=None, password=None):
        """
        Authenticate with zync
        """
        url = '%s/validate.php' % (self.url,)
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
    def __init__(self, script_name, token, timeout=10.0, application=None):
        """
        Create a Zync object, for interacting with the ZYNC service
        """

        validate = True
        if application == 'maya':
            try:
                import maya.mel
                api_version = maya.mel.eval('about -api')
                if api_version < 201400:
                    print 'ZYNC WARNING: Disabling SSL validation to accomodate old Maya libraries. To re-enable validation, please use Maya 2014 or higher.'
                    validate = False
                else:
                    validate = True
            except:
                validate = True
            
        super(Zync, self).__init__(script_name, token, timeout=timeout, validate=validate)

        self.CONFIG = self.get_config()
        self.INSTANCE_TYPES = self.get_instance_types()
        self.FEATURES = self.get_enabled_features()
        self.MAYA_RENDERERS = self.get_maya_renderers()
        self.JOB_SUBTYPES = self.get_job_subtypes()

    def list(self, max=100, app=None):
        """
        Returns a list of all of the jobs on Zync
        """
        url = '%s/lib/get_jobs.php' % (self.url,)
        params = dict(max=max)
        url = '?'.join((url, urlencode(params)))
        resp, content = self.http.request(url, 'GET', headers=headers) 

        return load_json(content)

    def get_project_list(self):
        url = '%s/lib/get_project_list.php' % (self.url,)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        return load_json(content)

    def get_project_name(self, in_file):
        """
        Takes the name of a file - either a Maya or Nuke script - and returns
        the name of the project it belongs to.
        """
        params = {'file': in_file}
        url = '%s/lib/get_project_name.php?%s' % (self.url, urlencode(params))
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        return load_json(content)

    def get_maya_output_path(self, in_file):
        params = {'file': in_file}
        url = '%s/lib/get_maya_output.php?%s' % (self.url, urlencode(params))
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        return load_json(content)

    def get_config(self, var=None):
        url = '%s/lib/get_config_api.php' % (self.url,)
        headers = self.set_cookie()
        if var == None:
            resp, content = self.http.request(url, 'GET', headers=headers)
            try:
                return load_json(content)
            except ValueError:
                raise ZyncError(content)
        else:
            params = {'var': var}
            url += '?%s' % (urlencode(params),)
            resp, content = self.http.request(url, 'GET', headers=headers)
            return content

    def get_instance_types(self):
        url = '%s/lib/get_instance_types.php' % (self.url,)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        response_obj = load_json(content)
        if response_obj['code'] == 1:
            raise ZyncError('Could not retrieve list of instance types: %s' % (response_obj['response'],))
        return response_obj['response']

    def get_enabled_features(self):
        url = '%s/lib/get_enabled_features.php' % (self.url,)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        response_obj = load_json(content)
        if response_obj['code'] == 1:
            raise ZyncError('Could not retrieve list of enabled features: %s' % (response_obj['response'],))
        return response_obj['response']

    def get_maya_renderers(self):
        url = '%s/lib/get_maya_renderers.php' % (self.url,)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        response_obj = load_json(content)
        if response_obj['code'] == 1:
            raise ZyncError('Could not retrieve list of Maya renderers: %s' % (response_obj['response'],))
        return response_obj['response']

    def get_job_subtypes(self):
        url = '%s/lib/get_job_subtypes.php' % (self.url,)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        response_obj = load_json(content)
        if response_obj['code'] == 1:
            raise ZyncError('Could not retrieve list of Job Types: %s' % (response_obj['response'],))
        return response_obj['response']

    def get_job_params(self, job_id):
        params = {'job_id': job_id}
        url = '%s/lib/get_job_params.php?%s' % (self.url, urlencode(params))
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        return content

    def get_triggers(self, user=None, show_seen=False):
        """
        Returns a list of current trigger events in ZYNC
        """
        url = '%s/lib/get_triggers.php' % (self.url,) 
        params = {}
        if show_seen == True:
            params["show_seen"] = 1
        else:
            params["show_seen"] = 0
        if user != None:
            params["user"] = user
        url = '?'.join((url, urlencode(params)))
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)

        return json.loads(content)

    def submit_job(self, job_type, *args, **kwargs):
        job_type = job_type.lower()

        if job_type == 'nuke':
            JobSelect = NukeJob
        elif job_type == 'maya':
            JobSelect = MayaJob
        else:
            raise ZyncError('Unrecognized job_type "%s".' % (job_type,))

        self.job = JobSelect(self.cookie, self.url, validate=self.validate)

        # run job.preflight(). if preflight does not succeed, an error will be
        # thrown, so no need to check output here.
        self.job.preflight()

        return self.job.submit(*args, **kwargs)

    def submit(self, *args, **kwargs):
        """
        Wraps the submit method for the initialized job object.
        See the documentation for `NukeJob.submit()` and `MayaJob.submit()`
        """
        return self.job.submit(*args, **kwargs)

class Job(object):
    """
    ZYNC Job class
    """
    def __init__(self, cookie, url, validate=True):
        """
        The base ZYNC Job object, not useful on its own, but should be
        the parent for app specific Job implementations.
        """
        if cookie:
            self.cookie = cookie
        else:
            raise ZyncAuthenticationError('ZYNC Auth Failed')

        self.url = url
        self.validate = validate
        if self.validate:
            self.http = zync_lib.httplib2.Http()
        else:
            self.http = zync_lib.httplib2.Http(disable_ssl_certificate_validation=True) 
            print 'ZYNC WARNING: disabling SSL validation due to out-of-date system libraries. Please contact ZYNC Tech Support for more info on this issue.'
        self.job_type = None

    def set_cookie(self, headers={}, cookie=None):
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
        url = '%s/lib/retry_errors.php' % (self.url,)
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
        url = '%s/lib/set_job_status.php' % (self.url,)
        data = urlencode(dict(job_id=job_id, status=status))
        url = '?'.join((url, data))

        return self.http.request(url, 'GET')

    def get_preflight_checks(self):
        if self.job_type == None:
            raise ZyncError('job_type parameter not set. This is probably because your subclass of Job doesn\'t define it.')
        params = {'job_type': self.job_type}
        url = '%s/lib/get_preflight_checks.php?%s' % (self.url, urlencode(params)) 
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        content_obj = json.loads( content )
        if content_obj["code"] == 0:
            return content_obj["response"]
        else:
            raise ZyncError('Could not retrieve list of preflight checks: %s' % (content_obj['response'],)) 

    def preflight(self):
        """
        Run the Job's preflight, which performs checks for common mistakes before
        submitting the job to ZYNC.
        """
        #
        #   Get the list of preflight checks.
        #
        preflight_list = self.get_preflight_checks()
        #
        #   Set up the environment needed to run the API commands passed to us. If
        #   Exceptions occur when loading the app APIs, return, as we're probably
        #   running in an external script and don't have access to the API.
        #
        #   TODO: can we move these into the Job subclasses? kind of annoying to have
        #         app-specific code here, but AFAIK the imports have to happen in this
        #         function in order to persist.
        #
        if len(preflight_list) > 0:
            if self.job_type == 'maya':
                try:
                    import maya.cmds as cmds
                except:
                    return
            elif self.job_type == 'nuke':
                try:
                    import nuke
                except:
                    return
        #
        #   Run the preflight checks.
        #
        for preflight_obj in preflight_list:
            matches = []
            try:
                #
                #   eval() the API code passed to us, which must return either a string or a list.
                #
                api_result = eval( preflight_obj['api_call'] )
                #
                #   If its not a list or a tuple, turn it into a list.
                #
                if (not type(api_result) is list) and (not type(api_result) is tuple):
                    api_result = [ api_result ]
                #
                #   Look through the API result to see if the result meets the conditions laid
                #   out by the check.
                #
                for result_item in api_result:
                    if preflight_obj['operation_type'] == 'equal' and result_item in preflight_obj['condition']:
                        matches.append( str(result_item) )
                    elif preflight_obj['operation_type'] == 'not_equal' and result_item not in preflight_obj['condition']:
                        matches.append( str(result_item) )
            except Exception as e:
                continue
            #
            #   If there were any conditions matched, raise a ZyncPreflightError.
            #
            if len(matches) > 0:
                raise ZyncPreflightError(preflight_obj['error'].replace('%match%', ', '.join(matches)))

    def submit(self, params):
        """
        Submit a job to Zync
        """
        url = '%s/lib/submit_job_v2.php' % (self.url,)
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
        submit_params['job_subtype'] = 'render'

        submit_params.update(params)

        if 'scene_info' in submit_params:
            submit_params['scene_info'] = json.dumps(submit_params['scene_info'])

        headers = self.set_cookie(headers=headers)

        resp, content = self.http.request(url, 'POST', urlencode(submit_params),
                                          headers=headers)

        

        #
        #   A return code of 0 means the submission succeeded. Return the job ID.
        #   Otherwise, an error occurred, and the response field contains the error
        #   message; raise an error with that message.
        #
        response_obj = load_json(content)
        if response_obj['code'] != 0:
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
    def __init__(self, *args, **kwargs):
        super(NukeJob, self).__init__(*args, **kwargs)
        self.job_type = 'nuke'

    def submit(self, script_path, write_name, params=None):
        """
        Submits a Nuke Job to ZYNC.

        Nuke-specific submit parameters:
            write_node: The write node to render. Can be 'All' to render
                        all nodes.
        """
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
    def __init__(self, *args, **kwargs):
        super(MayaJob, self).__init__(*args, **kwargs)
        self.job_type = 'maya'

    def submit(self, file, params=None):
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
            'vray': V-Ray
            'mr': Mental Ray
            'arnold': Arnold
        """
        submit_params = {}
        submit_params['job_type'] = 'Maya'
        submit_params['file'] = file

        if params:
            submit_params.update(params)

        return super(MayaJob, self).submit(submit_params)

