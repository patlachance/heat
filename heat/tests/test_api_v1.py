# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


import sys
import socket
import nose
import mox
import json
import unittest
from nose.plugins.attrib import attr

import httplib
import json
import urlparse

from heat.common import config
from heat.common import context
from heat.engine import auth
from heat.openstack.common import cfg
from heat.openstack.common import rpc
import heat.openstack.common.rpc.common as rpc_common
from heat.common.wsgi import Request
from heat.api.aws import exception
import heat.api.v1.stacks as stacks


@attr(tag=['unit', 'api-v1-stacks', 'StackController'])
@attr(speed='fast')
class StackControllerTest(unittest.TestCase):
    '''
    Tests the API class which acts as the WSGI controller,
    the endpoint processing API requests after they are routed
    '''
    # Utility functions
    def _create_context(self, user='api_test_user'):
        ctx = context.get_admin_context()
        self.m.StubOutWithMock(ctx, 'username')
        ctx.username = user
        self.m.StubOutWithMock(auth, 'authenticate')
        return ctx

    def _dummy_GET_request(self, params={}):
        # Mangle the params dict into a query string
        qs = "&".join(["=".join([k, str(params[k])]) for k in params])
        environ = {'REQUEST_METHOD': 'GET', 'QUERY_STRING': qs}
        req = Request(environ)
        req.context = self._create_context()
        return req

    # The tests
    def test_stackid_addprefix(self):

        # Stub socket.gethostname so it returns "ahostname"
        self.m.StubOutWithMock(socket, 'gethostname')
        socket.gethostname().AndReturn("ahostname")

        self.m.ReplayAll()

        response = self.controller._stackid_addprefix({'StackName': 'Foo',
                                                       'StackId': str(123)})
        expected = {'StackName': 'Foo',
                    'StackId': 'ahostname:8000:stack/Foo/123'}
        self.assert_(response == expected)

    def test_list(self):
        # Format a dummy GET request to pass into the WSGI handler
        params = {'Action': 'ListStacks'}
        dummy_req = self._dummy_GET_request(params)

        # Stub out the RPC call to the engine with a pre-canned response
        engine_resp = {u'stacks': [
                        {u'stack_id': u'1',
                        u'updated_time': u'2012-07-09T09:13:11Z',
                        u'template_description': u'blah',
                        u'stack_status_reason': u'Stack successfully created',
                        u'creation_time': u'2012-07-09T09:12:45Z',
                        u'stack_name': u'wordpress',
                        u'stack_status': u'CREATE_COMPLETE'}]}
        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'show_stack',
                                    'args': {'stack_name': None,
                                    'params': dict(dummy_req.params)},
                                    'version': self.api_version}, None
                ).AndReturn(engine_resp)

        # Stub socket.gethostname so it returns "ahostname"
        self.m.StubOutWithMock(socket, 'gethostname')
        socket.gethostname().AndReturn("ahostname")

        self.m.ReplayAll()

        # Call the list controller function and compare the response
        result = self.controller.list(dummy_req)
        expected = {'ListStacksResponse': {'ListStacksResult':
            {'StackSummaries': [
            {u'StackId': u'ahostname:8000:stack/wordpress/1',
            u'LastUpdatedTime': u'2012-07-09T09:13:11Z',
            u'TemplateDescription': u'blah',
            u'StackStatusReason': u'Stack successfully created',
            u'CreationTime': u'2012-07-09T09:12:45Z',
            u'StackName': u'wordpress', u'StackStatus': u'CREATE_COMPLETE'}]}}}
        self.assertEqual(result, expected)

    def test_list_rmt_aterr(self):
        params = {'Action': 'ListStacks'}
        dummy_req = self._dummy_GET_request(params)

        # Insert an engine RPC error and ensure we map correctly to the
        # heat exception type
        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'show_stack',
                                    'args': {'stack_name': None,
                                    'params': dict(dummy_req.params)},
                                    'version': self.api_version}, None
                ).AndRaise(rpc_common.RemoteError("AttributeError"))

        self.m.ReplayAll()

        # Call the list controller function and compare the response
        result = self.controller.list(dummy_req)
        self.assert_(type(result) == exception.HeatInvalidParameterValueError)

    def test_list_rmt_interr(self):
        params = {'Action': 'ListStacks'}
        dummy_req = self._dummy_GET_request(params)

        # Insert an engine RPC error and ensure we map correctly to the
        # heat exception type
        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'show_stack',
                                    'args': {'stack_name': None,
                                    'params': dict(dummy_req.params)},
                                    'version': self.api_version}, None
                ).AndRaise(rpc_common.RemoteError("Exception"))

        self.m.ReplayAll()

        # Call the list controller function and compare the response
        result = self.controller.list(dummy_req)
        self.assert_(type(result) == exception.HeatInternalFailureError)

    def test_describe(self):
        # Format a dummy GET request to pass into the WSGI handler
        stack_name = u"wordpress"
        params = {'Action': 'DescribeStacks', 'StackName': stack_name}
        dummy_req = self._dummy_GET_request(params)

        # Stub out the RPC call to the engine with a pre-canned response
        # Note the engine returns a load of keys we don't actually use
        # so this is a subset of the real response format
        engine_resp = {u'stacks': [
            {u'stack_id': u'6',
            u'updated_time': u'2012-07-09T09:13:11Z',
            u'parameters':{
            u'DBUsername': {u'Default': u'admin'},
            u'LinuxDistribution': {u'Default': u'F16'},
            u'InstanceType': {u'Default': u'm1.large'},
            u'DBRootPassword': {u'Default': u'admin'},
            u'DBPassword': {u'Default': u'admin'},
            u'DBName': {u'Default': u'wordpress'}},
            u'outputs':
                [{u'output_key': u'WebsiteURL',
                u'description': u'URL for Wordpress wiki',
                u'output_value': u'http://10.0.0.8/wordpress'}],
            u'stack_status_reason': u'Stack successfully created',
            u'creation_time': u'2012-07-09T09:12:45Z',
            u'stack_name': u'wordpress',
            u'notification_topics': [],
            u'stack_status': u'CREATE_COMPLETE',
            u'description': u'blah',
            u'disable_rollback': True,
            u'timeout_mins':60,
            u'capabilities':[]}]}

        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'show_stack',
            'args': {'stack_name': stack_name,
                     'params': dict(dummy_req.params)},
            'version': self.api_version}, None).AndReturn(engine_resp)

        # Stub socket.gethostname so it returns "ahostname"
        self.m.StubOutWithMock(socket, 'gethostname')
        socket.gethostname().AndReturn("ahostname")

        self.m.ReplayAll()

        # Call the list controller function and compare the response
        response = self.controller.describe(dummy_req)

        expected = {'DescribeStacksResponse': {'DescribeStacksResult':
                {'Stacks':
                [{'StackId': u'ahostname:8000:stack/wordpress/6',
                'StackStatusReason': u'Stack successfully created',
                'Description': u'blah',
                'Parameters':
                    [{'ParameterValue': u'admin',
                    'ParameterKey': u'DBUsername'},
                    {'ParameterValue': u'F16',
                    'ParameterKey': u'LinuxDistribution'},
                    {'ParameterValue': u'm1.large',
                    'ParameterKey': u'InstanceType'},
                    {'ParameterValue': u'admin',
                    'ParameterKey': u'DBRootPassword'},
                    {'ParameterValue': u'admin',
                    'ParameterKey': u'DBPassword'},
                    {'ParameterValue': u'wordpress',
                    'ParameterKey': u'DBName'}],
                'Outputs':
                    [{'OutputKey': u'WebsiteURL',
                    'OutputValue': u'http://10.0.0.8/wordpress',
                    'Description': u'URL for Wordpress wiki'}],
                'TimeoutInMinutes': 60,
                'CreationTime': u'2012-07-09T09:12:45Z',
                'Capabilities': [],
                'StackName': u'wordpress',
                'NotificationARNs': [],
                'StackStatus': u'CREATE_COMPLETE',
                'DisableRollback': True,
                'LastUpdatedTime': u'2012-07-09T09:13:11Z'}]}}}

        self.assert_(response == expected)

    def test_describe_aterr(self):
        stack_name = "wordpress"
        params = {'Action': 'DescribeStacks', 'StackName': stack_name}
        dummy_req = self._dummy_GET_request(params)

        # Insert an engine RPC error and ensure we map correctly to the
        # heat exception type
        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'show_stack',
            'args': {'stack_name': stack_name,
            'params': dict(dummy_req.params)},
            'version': self.api_version}, None
            ).AndRaise(rpc_common.RemoteError("AttributeError"))

        self.m.ReplayAll()

        result = self.controller.describe(dummy_req)
        self.assert_(type(result) == exception.HeatInvalidParameterValueError)

    def test_get_template_int_body(self):
        ''' Test the internal _get_template function '''
        params = {'TemplateBody': "abcdef"}
        dummy_req = self._dummy_GET_request(params)
        result = self.controller._get_template(dummy_req)
        expected = "abcdef"
        self.assert_(result == expected)

    # TODO : test the _get_template TemplateUrl case

    def test_create(self):
        # Format a dummy request
        stack_name = "wordpress"
        template = {u'Foo': u'bar'}
        json_template = json.dumps(template)
        params = {'Action': 'CreateStack', 'StackName': stack_name,
                  'TemplateBody': '%s' % json_template,
                  'TimeoutInMinutes': 30,
                  'Parameters.member.1.ParameterKey': 'InstanceType',
                  'Parameters.member.1.ParameterValue': 'm1.xlarge'}
        engine_parms = {u'InstanceType': u'm1.xlarge'}
        engine_args = {'timeout_mins': u'30'}
        dummy_req = self._dummy_GET_request(params)

        # Stub out the RPC call to the engine with a pre-canned response
        engine_resp = {u'StackName': u'wordpress', u'StackId': 1}

        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'create_stack',
            'args':
            {'stack_name': stack_name,
            'template': template,
            'params': engine_parms,
            'args': engine_args},
            'version': self.api_version}, None).AndReturn(engine_resp)

        # Stub socket.gethostname so it returns "ahostname"
        self.m.StubOutWithMock(socket, 'gethostname')
        socket.gethostname().AndReturn("ahostname")

        self.m.ReplayAll()

        response = self.controller.create(dummy_req)

        expected = {'CreateStackResponse': {'CreateStackResult':
                        {u'StackName': u'wordpress',
                        u'StackId': u'ahostname:8000:stack/wordpress/1'}}}

        self.assert_(response == expected)

    def test_create_err_no_template(self):
        # Format a dummy request with a missing template field
        stack_name = "wordpress"
        params = {'Action': 'CreateStack', 'StackName': stack_name}
        dummy_req = self._dummy_GET_request(params)

        result = self.controller.create(dummy_req)
        self.assert_(type(result) == exception.HeatMissingParameterError)

    def test_create_err_inval_template(self):
        # Format a dummy request with an invalid TemplateBody
        stack_name = "wordpress"
        json_template = "!$%**_+}@~?"
        params = {'Action': 'CreateStack', 'StackName': stack_name,
                  'TemplateBody': '%s' % json_template}
        dummy_req = self._dummy_GET_request(params)

        result = self.controller.create(dummy_req)
        self.assert_(type(result) == exception.HeatInvalidParameterValueError)

    def test_create_err_rpcerr(self):
        # Format a dummy request
        stack_name = "wordpress"
        template = {u'Foo': u'bar'}
        json_template = json.dumps(template)
        params = {'Action': 'CreateStack', 'StackName': stack_name,
                  'TemplateBody': '%s' % json_template,
                  'TimeoutInMinutes': 30,
                  'Parameters.member.1.ParameterKey': 'InstanceType',
                  'Parameters.member.1.ParameterValue': 'm1.xlarge'}
        engine_parms = {u'InstanceType': u'm1.xlarge'}
        engine_args = {'timeout_mins': u'30'}
        dummy_req = self._dummy_GET_request(params)

        # Insert an engine RPC error and ensure we map correctly to the
        # heat exception type
        self.m.StubOutWithMock(rpc, 'call')

        rpc.call(dummy_req.context, self.topic, {'method': 'create_stack',
            'args':
            {'stack_name': stack_name,
            'template': template,
            'params': engine_parms,
            'args': engine_args},
            'version': self.api_version}, None
            ).AndRaise(rpc_common.RemoteError("AttributeError"))

        self.m.ReplayAll()

        result = self.controller.create(dummy_req)

        self.assert_(type(result) == exception.HeatInvalidParameterValueError)

    def test_update(self):
        # Format a dummy request
        stack_name = "wordpress"
        template = {u'Foo': u'bar'}
        json_template = json.dumps(template)
        params = {'Action': 'UpdateStack', 'StackName': stack_name,
                  'TemplateBody': '%s' % json_template,
                  'Parameters.member.1.ParameterKey': 'InstanceType',
                  'Parameters.member.1.ParameterValue': 'm1.xlarge'}
        engine_parms = {u'InstanceType': u'm1.xlarge'}
        engine_args = {}
        dummy_req = self._dummy_GET_request(params)

        # Stub out the RPC call to the engine with a pre-canned response
        engine_resp = {u'StackName': u'wordpress', u'StackId': 1}

        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'update_stack',
            'args':
            {'stack_name': stack_name,
            'template': template,
            'params': engine_parms,
            'args': engine_args},
            'version': self.api_version}, None).AndReturn(engine_resp)

        # Stub socket.gethostname so it returns "ahostname"
        self.m.StubOutWithMock(socket, 'gethostname')
        socket.gethostname().AndReturn("ahostname")

        self.m.ReplayAll()

        response = self.controller.update(dummy_req)

        expected = {'UpdateStackResponse': {'UpdateStackResult':
                        {u'StackName': u'wordpress',
                        u'StackId': u'ahostname:8000:stack/wordpress/1'}}}

        self.assert_(response == expected)

    def test_create_or_update_err(self):
        result = self.controller.create_or_update(req={}, action="dsdgfdf")
        self.assert_(type(result) == exception.HeatInternalFailureError)

    def test_get_template(self):
        # Format a dummy request
        stack_name = "wordpress"
        template = {u'Foo': u'bar'}
        params = {'Action': 'GetTemplate', 'StackName': stack_name}
        dummy_req = self._dummy_GET_request(params)

        # Stub out the RPC call to the engine with a pre-canned response
        engine_resp = template

        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'get_template',
            'args':
            {'stack_name': stack_name,
            'params': dict(dummy_req.params)},
            'version': self.api_version}, None).AndReturn(engine_resp)

        self.m.ReplayAll()

        response = self.controller.get_template(dummy_req)

        expected = {'GetTemplateResponse': {'GetTemplateResult':
                        {'TemplateBody': template}}}

        self.assert_(response == expected)

    def test_get_template_err_rpcerr(self):
        stack_name = "wordpress"
        template = {u'Foo': u'bar'}
        params = {'Action': 'GetTemplate', 'StackName': stack_name}
        dummy_req = self._dummy_GET_request(params)

        # Insert an engine RPC error and ensure we map correctly to the
        # heat exception type
        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'get_template',
            'args':
            {'stack_name': stack_name,
            'params': dict(dummy_req.params)},
            'version': self.api_version}, None
            ).AndRaise(rpc_common.RemoteError("AttributeError"))

        self.m.ReplayAll()

        result = self.controller.get_template(dummy_req)

        self.assert_(type(result) == exception.HeatInvalidParameterValueError)

    def test_get_template_err_none(self):
        stack_name = "wordpress"
        template = {u'Foo': u'bar'}
        params = {'Action': 'GetTemplate', 'StackName': stack_name}
        dummy_req = self._dummy_GET_request(params)

        # Stub out the RPC call to the engine to return None
        # this test the "no such stack" error path
        engine_resp = None

        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'get_template',
            'args':
            {'stack_name': stack_name,
            'params': dict(dummy_req.params)},
            'version': self.api_version}, None).AndReturn(engine_resp)

        self.m.ReplayAll()

        result = self.controller.get_template(dummy_req)

        self.assert_(type(result) == exception.HeatInvalidParameterValueError)

    def test_validate_err_no_template(self):
        # Format a dummy request with a missing template field
        stack_name = "wordpress"
        params = {'Action': 'ValidateTemplate'}
        dummy_req = self._dummy_GET_request(params)

        result = self.controller.validate_template(dummy_req)
        self.assert_(type(result) == exception.HeatMissingParameterError)

    def test_validate_err_inval_template(self):
        # Format a dummy request with an invalid TemplateBody
        json_template = "!$%**_+}@~?"
        params = {'Action': 'ValidateTemplate',
                  'TemplateBody': '%s' % json_template}
        dummy_req = self._dummy_GET_request(params)

        result = self.controller.validate_template(dummy_req)
        self.assert_(type(result) == exception.HeatInvalidParameterValueError)

    def test_delete(self):
        # Format a dummy request
        stack_name = "wordpress"
        params = {'Action': 'DeleteStack', 'StackName': stack_name}
        dummy_req = self._dummy_GET_request(params)

        # Stub out the RPC call to the engine with a pre-canned response
        # Engine returns None when delete successful
        engine_resp = None

        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'delete_stack',
            'args':
            {'stack_name': stack_name,
            'params': dict(dummy_req.params)},
            'version': self.api_version}, None).AndReturn(engine_resp)

        self.m.ReplayAll()

        response = self.controller.delete(dummy_req)

        expected = {'DeleteStackResponse': {'DeleteStackResult': ''}}

        self.assert_(response == expected)

    def test_delete_err_rpcerr(self):
        stack_name = "wordpress"
        params = {'Action': 'DeleteStack', 'StackName': stack_name}
        dummy_req = self._dummy_GET_request(params)

        # Insert an engine RPC error and ensure we map correctly to the
        # heat exception type
        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'delete_stack',
            'args':
            {'stack_name': stack_name,
            'params': dict(dummy_req.params)},
            'version': self.api_version}, None
            ).AndRaise(rpc_common.RemoteError("AttributeError"))

        self.m.ReplayAll()

        result = self.controller.delete(dummy_req)

        self.assert_(type(result) == exception.HeatInvalidParameterValueError)

    def test_events_list(self):
        # Format a dummy request
        stack_name = "wordpress"
        params = {'Action': 'DescribeStackEvents', 'StackName': stack_name}
        dummy_req = self._dummy_GET_request(params)

        # Stub out the RPC call to the engine with a pre-canned response
        engine_resp = {u'events': [{u'stack_name': u'wordpress',
                        u'event_time': u'2012-07-23T13:05:39Z',
                        u'stack_id': 6,
                        u'logical_resource_id': u'WikiDatabase',
                        u'resource_status_reason': u'state changed',
                        u'event_id': 42,
                        u'resource_status': u'IN_PROGRESS',
                        u'physical_resource_id': None,
                        u'resource_properties':
                            {u'UserData': u'blah'},
                        u'resource_type': u'AWS::EC2::Instance'}]}

        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'list_events',
            'args':
            {'stack_name': stack_name,
            'params': dict(dummy_req.params)},
            'version': self.api_version}, None).AndReturn(engine_resp)

        # Stub socket.gethostname so it returns "ahostname"
        self.m.StubOutWithMock(socket, 'gethostname')
        socket.gethostname().AndReturn("ahostname")

        self.m.ReplayAll()

        response = self.controller.events_list(dummy_req)

        expected = {'DescribeStackEventsResponse':
            {'DescribeStackEventsResult':
            {'StackEvents':
                [{'EventId': 42,
                'StackId': u'ahostname:8000:stack/wordpress/6',
                'ResourceStatus': u'IN_PROGRESS',
                'ResourceType': u'AWS::EC2::Instance',
                'Timestamp': u'2012-07-23T13:05:39Z',
                'StackName': u'wordpress',
                'ResourceProperties': {u'UserData': u'blah'},
                'PhysicalResourceId': None,
                'ResourceStatusData': u'state changed',
                'LogicalResourceId': u'WikiDatabase'}]}}}

        self.assert_(response == expected)

    def test_events_list_err_rpcerr(self):
        stack_name = "wordpress"
        params = {'Action': 'DescribeStackEvents', 'StackName': stack_name}
        dummy_req = self._dummy_GET_request(params)

        # Insert an engine RPC error and ensure we map correctly to the
        # heat exception type
        self.m.StubOutWithMock(rpc, 'call')
        rpc.call(dummy_req.context, self.topic, {'method': 'list_events',
            'args':
            {'stack_name': stack_name,
            'params': dict(dummy_req.params)},
            'version': self.api_version}, None
            ).AndRaise(rpc_common.RemoteError("Exception"))

        self.m.ReplayAll()

        result = self.controller.events_list(dummy_req)

        self.assert_(type(result) == exception.HeatInternalFailureError)

    def test_describe_stack_resource(self):
        # Format a dummy request
        stack_name = "wordpress"
        params = {'Action': 'DescribeStackResource',
                  'StackName': stack_name,
                  'LogicalResourceId': "WikiDatabase"}
        dummy_req = self._dummy_GET_request(params)

        # Stub out the RPC call to the engine with a pre-canned response
        engine_resp = {u'description': u'',
                       u'stack_name': u'wordpress',
                       u'logical_resource_id': u'WikiDatabase',
                       u'resource_status_reason': None,
                       u'updated_time': u'2012-07-23T13:06:00Z',
                       u'stack_id': 6,
                       u'resource_status': u'CREATE_COMPLETE',
                       u'physical_resource_id':
                            u'a3455d8c-9f88-404d-a85b-5315293e67de',
                       u'resource_type': u'AWS::EC2::Instance',
                       u'metadata': {u'wordpress': []}}

        self.m.StubOutWithMock(rpc, 'call')
        args = {
            'stack_name': dummy_req.params.get('StackName'),
            'resource_name': dummy_req.params.get('LogicalResourceId'),
        }
        rpc.call(dummy_req.context, self.topic,
            {'method': 'describe_stack_resource',
            'args': args,
            'version': self.api_version}, None).AndReturn(engine_resp)

        # Stub socket.gethostname so it returns "ahostname"
        self.m.StubOutWithMock(socket, 'gethostname')
        socket.gethostname().AndReturn("ahostname")

        self.m.ReplayAll()

        response = self.controller.describe_stack_resource(dummy_req)

        expected = {'DescribeStackResourceResponse':
                    {'DescribeStackResourceResult':
                    {'StackResourceDetail':
                    {'StackId': u'ahostname:8000:stack/wordpress/6',
                    'ResourceStatus': u'CREATE_COMPLETE',
                    'Description': u'',
                    'ResourceType': u'AWS::EC2::Instance',
                    'ResourceStatusReason': None,
                    'LastUpdatedTimestamp': u'2012-07-23T13:06:00Z',
                    'StackName': u'wordpress',
                    'PhysicalResourceId':
                        u'a3455d8c-9f88-404d-a85b-5315293e67de',
                    'Metadata': {u'wordpress': []},
                    'LogicalResourceId': u'WikiDatabase'}}}}

        self.assert_(response == expected)

    def test_describe_stack_resources(self):
        # Format a dummy request
        stack_name = "wordpress"
        params = {'Action': 'DescribeStackResources',
                  'StackName': stack_name,
                  'LogicalResourceId': "WikiDatabase"}
        dummy_req = self._dummy_GET_request(params)

        # Stub out the RPC call to the engine with a pre-canned response
        engine_resp = [{u'description': u'',
                        u'stack_name': u'wordpress',
                        u'logical_resource_id': u'WikiDatabase',
                        u'resource_status_reason': None,
                        u'updated_time': u'2012-07-23T13:06:00Z',
                        u'stack_id': 6,
                        u'resource_status': u'CREATE_COMPLETE',
                        u'physical_resource_id':
                            u'a3455d8c-9f88-404d-a85b-5315293e67de',
                        u'resource_type': u'AWS::EC2::Instance',
                        u'metadata': {u'ensureRunning': u'true''true'}}]

        self.m.StubOutWithMock(rpc, 'call')
        args = {
            'stack_name': dummy_req.params.get('StackName'),
            'physical_resource_id': None,
            'logical_resource_id': dummy_req.params.get('LogicalResourceId'),
        }
        rpc.call(dummy_req.context, self.topic,
            {'method': 'describe_stack_resources',
            'args': args,
            'version': self.api_version}, None).AndReturn(engine_resp)

        # Stub socket.gethostname so it returns "ahostname"
        self.m.StubOutWithMock(socket, 'gethostname')
        socket.gethostname().AndReturn("ahostname")

        self.m.ReplayAll()

        response = self.controller.describe_stack_resources(dummy_req)

        expected = {'DescribeStackResourcesResponse':
                    {'DescribeStackResourcesResult':
                    {'StackResources':
                        [{'StackId': u'ahostname:8000:stack/wordpress/6',
                        'ResourceStatus': u'CREATE_COMPLETE',
                        'Description': u'',
                        'ResourceType': u'AWS::EC2::Instance',
                        'Timestamp': u'2012-07-23T13:06:00Z',
                        'ResourceStatusReason': None,
                        'StackName': u'wordpress',
                        'PhysicalResourceId':
                            u'a3455d8c-9f88-404d-a85b-5315293e67de',
                        'LogicalResourceId': u'WikiDatabase'}]}}}

        self.assert_(response == expected)

    def test_describe_stack_resources_err_inval(self):
        # Format a dummy request containing both StackName and
        # PhysicalResourceId, which is invalid and should throw a
        # HeatInvalidParameterCombinationError
        stack_name = "wordpress"
        params = {'Action': 'DescribeStackResources',
                  'StackName': stack_name,
                  'PhysicalResourceId': "123456"}
        dummy_req = self._dummy_GET_request(params)
        ret = self.controller.describe_stack_resources(dummy_req)
        self.assert_(type(ret) ==
            exception.HeatInvalidParameterCombinationError)

    def test_list_stack_resources(self):
        # Format a dummy request
        stack_name = "wordpress"
        params = {'Action': 'ListStackResources',
                  'StackName': stack_name}
        dummy_req = self._dummy_GET_request(params)

        # Stub out the RPC call to the engine with a pre-canned response
        engine_resp = [{u'description': u'',
                        u'stack_name': u'wordpress',
                        u'logical_resource_id': u'WikiDatabase',
                        u'resource_status_reason': None,
                        u'updated_time': u'2012-07-23T13:06:00Z',
                        u'stack_id': 6,
                        u'resource_status': u'CREATE_COMPLETE',
                        u'physical_resource_id':
                            u'a3455d8c-9f88-404d-a85b-5315293e67de',
                        u'resource_type': u'AWS::EC2::Instance',
                        u'metadata': {}}]

        self.m.StubOutWithMock(rpc, 'call')
        args = {
            'stack_name': dummy_req.params.get('StackName'),
        }
        rpc.call(dummy_req.context, self.topic,
            {'method': 'list_stack_resources',
            'args': args,
            'version': self.api_version}, None).AndReturn(engine_resp)

        self.m.ReplayAll()

        response = self.controller.list_stack_resources(dummy_req)

        expected = {'ListStackResourcesResponse': {'ListStackResourcesResult':
                    {'StackResourceSummaries':
                    [{'ResourceStatus': u'CREATE_COMPLETE',
                    'ResourceType': u'AWS::EC2::Instance',
                    'ResourceStatusReason': None,
                    'LastUpdatedTimestamp': u'2012-07-23T13:06:00Z',
                    'PhysicalResourceId':
                        u'a3455d8c-9f88-404d-a85b-5315293e67de',
                     'LogicalResourceId': u'WikiDatabase'}]}}}

        self.assert_(response == expected)

    def setUp(self):
        self.maxDiff = None
        self.m = mox.Mox()

        config.register_engine_opts()
        cfg.CONF.set_default('engine_topic', 'engine')
        cfg.CONF.set_default('host', 'host')
        self.topic = '%s.%s' % (cfg.CONF.engine_topic, cfg.CONF.host)
        self.api_version = '1.0'

        # Create WSGI controller instance
        class DummyConfig():
            bind_port = 8000
        cfgopts = DummyConfig()
        self.controller = stacks.StackController(options=cfgopts)
        print "setup complete"

    def tearDown(self):
        self.m.UnsetStubs()
        self.m.VerifyAll()
        print "teardown complete"


if __name__ == '__main__':
    sys.argv.append(__file__)
    nose.main()
