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
        if response_obj['code'] == 0:
            return resp.get('set-cookie')
        else:
            raise ZyncAuthenticationError(response_obj['response'])

    def login(self, username=None, password=None):
        """
        Elevate your session's permission level by authenticating with your username
        and password. This is not required for most methods in the class - the main
        exception is submit_job(), which does require user/pass authentication.
        """
        if self.up():
            self.cookie = self.__auth(self.script_name, self.token, username=username, password=password)
        else:
            raise ZyncConnectionError('ZYNC is down at URL: %s' % self.url)

class Zync(HTTPBackend):
    """
    The entry point to the ZYNC service. Initialize this with your script name
    and token to use most API methods.
    """

    def __init__(self, script_name, token, timeout=10.0, application=None):
        """
        Create a Zync object, for interacting with the ZYNC service.
        """
        #
        #   As of 4/14, with the release of Maya 2015, Autodesk has stopped supporting
        #   Maya 2013. 2013's included OpenSSL is out of date and doesn't work with 
        #   many current SSL certificates, so we have to disable certificate validation.
        #   To ensure security, use Maya 2014 or higher.
        #
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
        #
        #   Call the HTTPBackend.__init__() method.
        #
        super(Zync, self).__init__(script_name, token, timeout=timeout, validate=validate)
        #
        #   Initialize class variables by pulling various info from ZYNC.
        #
        self.CONFIG = self.get_config()
        self.INSTANCE_TYPES = self.get_instance_types()
        self.FEATURES = self.get_enabled_features()
        self.JOB_SUBTYPES = self.get_job_subtypes()
        self.MAYA_RENDERERS = self.get_maya_renderers()

    def get_config(self, var=None):
        """
        Get your site's configuration settings. Use the "var" argument to
        get a specific value, or leave it out to get all values.
        """
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
        """
        Get a list of instance types available to your site.
        """
        url = '%s/lib/get_instance_types.php' % (self.url,)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        response_obj = load_json(content)
        if response_obj['code'] == 1:
            raise ZyncError('Could not retrieve list of instance types: %s' % (response_obj['response'],))
        return response_obj['response']

    def get_enabled_features(self):
        """
        Get a list of enabled features available to your site.
        """
        url = '%s/lib/get_enabled_features.php' % (self.url,)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        response_obj = load_json(content)
        if response_obj['code'] == 1:
            raise ZyncError('Could not retrieve list of enabled features: %s' % (response_obj['response'],))
        return response_obj['response']

    def get_job_subtypes(self):
        """
        Get a list of job subtypes available to your site. This will
        typically only be "render" - in the future ZYNC will likely support
        other subtypes like Texture Baking, etc.
        """
        url = '%s/lib/get_job_subtypes.php' % (self.url,)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        response_obj = load_json(content)
        if response_obj['code'] == 1:
            raise ZyncError('Could not retrieve list of Job Types: %s' % (response_obj['response'],))
        return response_obj['response']

    def get_maya_renderers(self):
        """
        Get a list of Maya renderers available to your site.
        """
        url = '%s/lib/get_maya_renderers.php' % (self.url,)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        response_obj = load_json(content)
        if response_obj['code'] == 1:
            raise ZyncError('Could not retrieve list of Maya renderers: %s' % (response_obj['response'],))
        return response_obj['response']

    def get_project_list(self):
        """
        Get a list of existing ZYNC projects on your site.
        """
        url = '%s/lib/get_project_list.php' % (self.url,)
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        return load_json(content)

    def get_project_name(self, in_file):
        """
        Takes the name of a file - either a Maya or Nuke script - and returns
        the default ZYNC project name for it.
        """
        params = {'file': in_file}
        url = '%s/lib/get_project_name.php?%s' % (self.url, urlencode(params))
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        return load_json(content)

    def get_jobs(self, max=100):
        """
        Returns a list of existing ZYNC jobs. 
        """
        url = '%s/lib/get_jobs.php' % (self.url,)
        params = dict(max=max)
        url = '?'.join((url, urlencode(params)))
        resp, content = self.http.request(url, 'GET', headers=headers) 
        return load_json(content)

    def get_job_details(self, job_id):
        """
        Get a list of a specific job's details.
        """
        params = {'job_id': job_id}
        url = '%s/lib/get_job_params.php?%s' % (self.url, urlencode(params))
        headers = self.set_cookie()
        resp, content = self.http.request(url, 'GET', headers=headers)
        return content

    def submit_job(self, job_type, *args, **kwargs):
        """
        Submit a new job to ZYNC.
        """
        #
        #   Select a Job subclass based on the job_type argument.
        #
        job_type = job_type.lower()
        if job_type == 'nuke':
            JobSelect = NukeJob
        elif job_type == 'maya':
            JobSelect = MayaJob
        elif job_type == 'arnold':
            JobSelect = ArnoldJob
        else:
            raise ZyncError('Unrecognized job_type "%s".' % (job_type,))
        #
        #   Initialize the Job subclass.
        #
        self.job = JobSelect(self.cookie, self.url, validate=self.validate)
        #
        #   Run job.preflight(). If preflight does not succeed, an error will be
        #   thrown, so no need to check output here.
        #
        self.job.preflight()
        #
        #   Submit the job and return the output of that method.
        #
        return self.job.submit(*args, **kwargs)

    def submit(self, *args, **kwargs):
        """
        Wraps the submit method for the initialized job object.
        See the documentation for `NukeJob.submit()` and `MayaJob.submit()`
        """
        return self.job.submit(*args, **kwargs)

class Job(object):
    """
    ZYNC Job main class.
    """
    def __init__(self, cookie, url, validate=True):
        """
        The base ZYNC Job object, not useful on its own, but should be
        the parent for application-specific Job implementations.
        """
        if cookie:
            self.cookie = cookie
        else:
            raise ZyncAuthenticationError('ZYNC Authentication failed.')

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
        ZyncAuthenticationError if cookie doesn't exist.
        """
        if cookie:
            self.cookie = cookie

        if self.cookie:
            headers['Cookie'] = self.cookie
            return headers
        else:
            raise ZyncAuthenticationError('ZYNC Auth Failed')

    def details(self, job_id):
        """
        Returns a dictionary of the job details.
        """
        url = '/'.join((self.url, 'lib', 'get_job_params.php'))
        data = urlencode({'job_id': job_id})
        url = '?'.join((url, data))
        resp, content = self.http.request(url, 'GET')
        return load_json(content)

    def set_status(self, job_id, status):
        """
        Sets the job status for the given job. This is the method by which most
        job controls are initiated.
        """
        url = '%s/lib/set_job_status.php' % (self.url,)
        data = urlencode(dict(job_id=job_id, status=status))
        url = '?'.join((url, data))
        return self.http.request(url, 'GET')

    def cancel(self, job_id):
        """
        Cancels the given job.
        """
        return self.set_status(job_id, 'canceled')

    def resume(self, job_id):
        """
        Resumes the given job.
        """
        return self.set_status(job_id, 'resume')

    def pause(self, job_id):
        """
        Pauses the given job.
        """
        return self.set_status(job_id, 'paused')

    def unpause(self, job_id):
        """
        Unpauses the given job.
        """
        return self.set_status(job_id, 'unpaused')

    def restart(self, job_id):
        """
        Requeues the given job.
        """
        return self.set_status(job_id, 'queued')

    def retry(self, job_id):
        """
        Retries the errored tasks for the given job ID.
        """
        url = '%s/lib/retry_errors.php' % (self.url,)
        data = urlencode({'job_id': job_id})
        url = '?'.join((url, data))
        return self.http.request(url, 'GET')

    def get_preflight_checks(self):
        """
        Gets a list of preflight checks for the current job type.
        """
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
        Submit a new job to ZYNC.
        """
        #
        #   Build the base URL and headers.
        #
        url = '%s/lib/submit_job_v2.php' % (self.url,)
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        #
        #   The submit_params dict will store most job options. Build 
        #   some defaults in; most of these will be overridden by the
        #   submission script.
        #
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
        #
        #   Update submit_params with any passed in params.
        #
        submit_params.update(params)
        #
        #   Special case for the "scene_info" parameter, which is JSON, so
        #   we'll encode it into a string.
        #
        if 'scene_info' in submit_params:
            submit_params['scene_info'] = json.dumps(submit_params['scene_info'])
        #
        #   Add the auth cookie to the headers.
        #
        headers = self.set_cookie(headers=headers)
        #
        #   Fire off the HTTP request to make the job submission.
        #
        resp, content = self.http.request(url, 'POST', urlencode(submit_params), headers=headers)
        #
        #   A return code of 0 means the submission succeeded. Return the job ID.
        #   Otherwise, an error occurred, and the response field contains the error
        #   message; raise an error with that message.
        #
        response_obj = load_json(content)
        if response_obj['code'] != 0:
            raise ZyncError('Could not submit job: %s' % (response_obj['response'],))
        return response_obj['response']
 
class NukeJob(Job):
    """
    Encapsulates Nuke-specific Job functions.
    """
    def __init__(self, *args, **kwargs):
        #
        #   Just run Job.__init__(), and set the job_type.
        #
        super(NukeJob, self).__init__(*args, **kwargs)
        self.job_type = 'nuke'

    def submit(self, script_path, write_name, params=None):
        """
        Submits a Nuke job to ZYNC.

        Nuke-specific submit parameters. * == required.

        * write_node: The write node to render. Can be 'All' to render
            all nodes.

        * frange: The frame range to render.

        * chunk_size: The number of frames to render per task.

        step: The frame step, i.e. a step of 1 will render very frame,
            a step of 2 will render every other frame. Setting step > 1
            will cause chunk_size to be set to 1. Defaults to 1.

        """
        #
        #   Build default params, and update them with what's been passed
        #   in.
        #
        submit_params = {}
        submit_params['job_type'] = 'Nuke'
        submit_params['write_node'] = write_name
	submit_params['file'] = script_path 
        if params:
            submit_params.update(params)
        #
        #   Fire Job.submit() to submit the job.
        #
        return super(NukeJob, self).submit(submit_params)

class MayaJob(Job):
    """
    Encapsulates Maya-specific job functions.
    """
    def __init__(self, *args, **kwargs):
        #
        #   Just run Job.__init__(), and set the job_type.
        #
        super(MayaJob, self).__init__(*args, **kwargs)
        self.job_type = 'maya'

    def submit(self, file, params=None):
        """
        Submits a Maya job to ZYNC.

        Maya-specific submit parameters. * == required.

        * camera: The name of the render camera.

        * xres: The output image x resolution.

        * yres: The output image y resolution.

        * chunk_size: The number of frames to render per task.

        * renderer: The renderer to use. A list of available renderers
            can be retrieved with Zync.get_maya_renderers().

        * out_path: The path to which output frames will be downloaded to.
            Use a local path as it appears to you.

        * project: The local path of your Maya project. Used to resolve all
            relative paths.

        * frange: The frame range to render.

        * scene_info: A dict of information about your Maya scene to help
            ZYNC prepare its environment properly.

                Required:

                    files: A list of files required to render your scene.

                    extension: The file extension of your rendered frames.

                    version: The Maya version in use.

                    render_layers: A list of ALL render layers in your scene, not just
                        those being rendered.

                Optional:

                    references: A list of references in use in your scene. Default: []

                    unresolved_references: A list of unresolved references in your scene.
                        Helps ZYNC find all references. Default: []

                    plugins: A list of plugins in use in your scene. Default: ['Mayatomr']

                    arnold_version: If rendering with the Arnold renderer, the Arnold
                        version in use. Required for Arnold jobs. Default: None

                    vray_version: If rendering with the Vray renderer, the Vray version in use.
                        Required for Vray jobs. Default: None

                    file_prefix: The file name prefix used in your scene. Default: ['', {}]
                        The structure is a two-element list, where the first element is the
                        global prefix and the second element is a dict of each layer override.
                        Example:
                            ['global_scene_prefix', {
                                layer1: 'layer1_prefix',
                                layer2: 'layer2_prefix'
                            }]

                    padding: The frame padding in your scene. Default: None

                    bake_sets: A dict of all Bake Sets in your scene. Required for Bake
                        jobs. Bake jobs are in beta and are probably not available for
                        your site. Default: {}

                    render_passes: A dict of render passes being renderered, by render layer.
                        Default: {}
                        Example: {'render_layer1': ['refl', 'beauty'], 'render_layer2': ['other_pass']}

            layers: A list of render layers to be rendered. Not required, but either layers or
                bake_sets must be provided. Default: []
    
            bake_sets: A list of Bake Sets to be baked out. Not required, but either layers or
                bake_sets must be provided. Bake jobs are currently in beta and are probably not
                available to your site yet. Default: []

            step: The frame step to render, i.e. a step of 1 will render very frame,
                a step of 2 will render every other frame. Setting step > 1
                will cause chunk_size to be set to 1. Default: 1

            use_mi: Whether to use Mental Ray Standalone to render. Only used for Mental Ray jobs. 
                This option is required for most sites. Default: 0

            use_vrscene: Whether to use Vray Standalone to render. Only used for Vray jobs.
                for Vray jobs. Default: 0

            vray_nightly: When rendering Vray, whether to use the latest Vray nightly build to render.
                Only used for Vray jobs. Default: 0

            ignore_plugin_errors: Whether to ignore errors about missing plugins. WARNING: if you
                set this to 1 and the missing plugins are doing anything important in your scene,
                it is extremely likely your job will render incorrectly, or not at all. USE CAUTION.

            use_ass: Whether to use Arnold Standalone (kick) to render. Only used for Arnold jobs. Default: 0

        """
        #
        #   Set some default params, and update them with what's been passed in.
        #
        submit_params = {}
        submit_params['job_type'] = 'Maya'
        submit_params['file'] = file
        if params:
            submit_params.update(params)
        #
        #   Fire Job.submit() to submit the job.
        #
        return super(MayaJob, self).submit(submit_params)

class ArnoldJob(Job):
    """
    Encapsulates Arnold-specific job functions.
    """
    def __init__(self, *args, **kwargs):
        #
        #   Just run Job.__init__(), and set the job_type.
        #
        super(ArnoldJob, self).__init__(*args, **kwargs)
        self.job_type = 'arnold'

    def submit(self, file, params=None):
        """
        Submits an Arnold job to ZYNC.

        Arnold-specific submit parameters. * == required.

        NOTE: the "file" param can contain a wildcard to render multiple Arnold
            scenes as part of the same job. E.g. "/path/to/render_scene.*.ass"

        * out_path: The output path to which all rendered frames will be downloaded.

        * camera: The name of the render camera.

        * xres: The output image x resolution.

        * yres: The output image y resolution.

        * scene_info: A dict of information about your Arnold scene to help
            ZYNC prepare its environment properly.

                Required:

                    extension: The file extension of your rendered frames.

                    arnold_version: The Arnold version in use.

                    padding: The frame padding in your scene.

                Optional:

                    files: A list of files required to render your scene. This is not
                        required as ZYNC will scan your scene to determine a file list.
                        But, you can use this element to force extra elements to be added.

        """
        #
        #   Build default params, and update with what's been passed in.
        #
        submit_params = {}
        submit_params['job_type'] = 'Arnold'
        submit_params['file'] = file
        if params:
            submit_params.update(params)
        #
        #   Fire Job.submit() to submit the job.
        #
        return super(ArnoldJob, self).submit(submit_params)

