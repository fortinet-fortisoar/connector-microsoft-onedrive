""" Copyright start
Copyright (C) 2008 - 2023 Fortinet Inc.
All rights reserved.
FORTINET CONFIDENTIAL & FORTINET PROPRIETARY SOURCE CODE
Copyright end """
import requests
from connectors.core.connector import get_logger, ConnectorError
from .microsoft_api_auth import MicrosoftAuth
from os.path import join
from integrations.crudhub import make_request
from connectors.cyops_utilities.builtins import upload_file_to_cyops, download_file_from_cyops

logger = get_logger("microsoft-onedrive")


class OneDrive(object):
    def __init__(self, config):
        self.server_url = config.get('resource').strip('/')
        if not self.server_url.startswith('https://') and not self.server_url.startswith('http://'):
            self.server_url = 'https://' + self.server_url
        self.verify_ssl = config.get('verify_ssl')
        self.ms_auth = MicrosoftAuth(config)
        self.connector_info = config.pop('connector_info', '')
        self.token = self.ms_auth.validate_token(config, self.connector_info)

    def make_rest_call(self, endpoint, params=None, json=None, payload=None, method='GET'):
        headers = {'Authorization': self.token, 'Content-Type': 'application/json'}
        service_url = self.server_url + endpoint
        logger.debug('Request URL {0}'.format(service_url))
        try:
            response = requests.request(method, service_url, data=payload, headers=headers, json=json, params=params,
                                        verify=self.verify_ssl)

            try:
                from connectors.debug_utils.curl_script import make_curl
                make_curl(method, endpoint, headers=headers, params=params, data=payload, verify_ssl=self.verify_ssl)
            except Exception as err:
                logger.error(f"Error in curl utils: {str(err)}")

            if response.ok:
                content_type = response.headers.get('Content-Type')
                if response.text != "" and 'application/json' in content_type:
                    return response.json()
                elif response.status_code == 204 and response.reason == 'No Content':
                    return {"message": "Not Found"}
                elif (response.status_code == 200 and response.reason == 'OK') or (
                        response.status_code == 202 and response.reason == 'Accepted'):
                    return {"message": "Successful"}
                else:
                    return response.content
            else:
                if response.text != "":
                    err_resp = response.json()
                    if "error" in err_resp:
                        error_msg = "{0}: {1}".format(err_resp.get('error').get('code'),
                                                      err_resp.get('error').get('message'))
                        raise ConnectorError(error_msg)
                    else:
                        raise ConnectorError(err_resp)
                else:
                    error_msg = '{0}: {1}'.format(response.status_code, response.reason)
                    raise ConnectorError(error_msg)
        except requests.exceptions.SSLError:
            logger.error('An SSL error occurred')
            raise ConnectorError('An SSL error occurred')
        except requests.exceptions.ConnectionError:
            logger.error('A connection error occurred')
            raise ConnectorError('A connection error occurred')
        except requests.exceptions.Timeout:
            logger.error('The request timed out')
            raise ConnectorError('The request timed out')
        except requests.exceptions.RequestException:
            logger.error('There was an error while handling the request')
            raise ConnectorError('There was an error while handling the request')
        except Exception as e:
            logger.error('{0}'.format(e))
            raise ConnectorError('{0}'.format(e))


def get_user_onedrive(config: dict, params: dict) -> dict:
    endpoint = f"/users/{params.get('user_id')}/drive"
    method = "GET"

    OD = OneDrive(config)
    response = OD.make_rest_call(endpoint=endpoint, method=method)
    return response


def get_document_library(config: dict, params: dict) -> dict:
    method = "GET"
    OD = OneDrive(config)
    if params.get('select_option') == "Group":
        endpoint = f"/groups/{params.get('g_id')}/drive"
    else:
        endpoint = f"/sites/{params.get('s_id')}/drive"
    response = OD.make_rest_call(endpoint=endpoint, method=method)
    return response


def get_drive_by_id(config: dict, params: dict) -> dict:
    method = "GET"
    OD = OneDrive(config)
    endpoint = f"/drives/{params.get('drive_id')}"
    response = OD.make_rest_call(endpoint=endpoint, method=method)
    return response


def create_folder(config: dict, params: dict) -> dict:
    method = "POST"
    associated_with = params.pop('associated_with')
    if associated_with == "Drive":
        endpoint = f"/drives/{params.pop('d_id')}/items/{params.pop('parent_item_id')}/children"
    else:
        endpoint = f"/users/{params.pop('u_id')}/drive/items/{params.pop('parent_item_id')}/children"
    OD = OneDrive(config)
    response = OD.make_rest_call(endpoint=endpoint, method=method, payload=params)
    return response


def download_file(config: dict, params: dict) -> dict:
    method = "GET"
    OD = OneDrive(config)
    associated_with = params.pop('associated_with')
    if associated_with == "Drive":
        endpoint = f"/drives/{params.pop('d_id')}/items/{params.pop('item_id')}/content"
    else:
        endpoint = f"/users/{params.pop('u_id')}/drive/items/{params.pop('item_id')}/content"
    response = OD.make_rest_call(endpoint=endpoint, method=method)
    return response


def upload_file(config: dict, params: dict) -> dict:
    method = "PUT"
    OD = OneDrive(config)
    file_iri = _handle_params(params)
    files = _submitFile(file_iri)

    method_data = {"document": files.get("document"), "filename": params.get('filename')}
    associated_with = params.pop('associated_with')
    if associated_with == "Drive":
        endpoint = f"/drives/{params.pop('d_id')}/items/{params.pop('parent_id')}:/{params.get('filename')}:/content"
    else:
        endpoint = f"/users/{params.pop('u_id')}/drive/items/{params.pop('parent_id')}:/{params.get('filename')}:/content"

    response = OD.make_rest_call(endpoint=endpoint, method=method, payload=files.get('document'))
    return response

def list_drives(config: dict, params: dict) -> dict:
    method = "GET"
    endpoint = "/drives"
    OD = OneDrive(config)
    response = OD.make_rest_call(endpoint=endpoint, method=method)
    return response

def _handle_params(params):
    value = str(params.get('value'))
    input_type = params.get('input')
    try:
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        if input_type == 'Attachment ID':
            if not value.startswith('/api/3/attachments/'):
                value = '/api/3/attachments/{0}'.format(value)
            attachment_data = make_request(value, 'GET')
            file_iri = attachment_data['file']['@id']
            file_name = attachment_data['file']['filename']
            return file_iri
        elif input_type == 'File IRI':
            if value.startswith('/api/3/files/'):
                return value
            else:
                raise ConnectorError('Invalid File IRI {0}'.format(value))
    except Exception as err:
        raise ConnectorError('Requested resource could not be found with input type "{0}" and value "{1}"'.format
                             (input_type, value.replace('/api/3/attachments/', '')))


def _submitFile(file_iri):
    try:
        file_path = join('/tmp', download_file_from_cyops(file_iri)['cyops_file_path'])
        with open(file_path, 'rb') as attachment:
            file_data = attachment.read()
        if file_data:
            files = {"document": file_data}
            return files
        raise ConnectorError('File size too large, submit file up to 32 MB')
    except Exception as Err:
        raise ConnectorError('Error in submitFile(): %s' % Err)


operations = {
    "get_user_onedrive": get_user_onedrive,
    "get_document_library": get_document_library,
    "get_drive_by_id": get_drive_by_id,
    "create_folder": create_folder,
    "download_file": download_file,
    "upload_file": upload_file,
    "list_drives": list_drives
}
