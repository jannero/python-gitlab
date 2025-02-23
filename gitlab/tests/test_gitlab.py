# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Mika Mäenpää <mika.j.maenpaa@tut.fi>,
#                    Tampere University of Technology
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import pickle
import tempfile
import json
import unittest
import unittest.mock

from httmock import HTTMock  # noqa
from httmock import response  # noqa
from httmock import urlmatch  # noqa
import requests

import gitlab
from gitlab import *  # noqa
from gitlab.v4.objects import *  # noqa


valid_config = b"""[global]
default = one
ssl_verify = true
timeout = 2

[one]
url = http://one.url
private_token = ABCDEF
"""


class TestSanitize(unittest.TestCase):
    def test_do_nothing(self):
        self.assertEqual(1, gitlab._sanitize(1))
        self.assertEqual(1.5, gitlab._sanitize(1.5))
        self.assertEqual("foo", gitlab._sanitize("foo"))

    def test_slash(self):
        self.assertEqual("foo%2Fbar", gitlab._sanitize("foo/bar"))

    def test_dict(self):
        source = {"url": "foo/bar", "id": 1}
        expected = {"url": "foo%2Fbar", "id": 1}
        self.assertEqual(expected, gitlab._sanitize(source))


class TestGitlabList(unittest.TestCase):
    def setUp(self):
        self.gl = Gitlab(
            "http://localhost", private_token="private_token", api_version=4
        )

    def test_build_list(self):
        @urlmatch(scheme="http", netloc="localhost", path="/api/v4/tests", method="get")
        def resp_1(url, request):
            headers = {
                "content-type": "application/json",
                "X-Page": 1,
                "X-Next-Page": 2,
                "X-Per-Page": 1,
                "X-Total-Pages": 2,
                "X-Total": 2,
                "Link": (
                    "<http://localhost/api/v4/tests?per_page=1&page=2>;" ' rel="next"'
                ),
            }
            content = '[{"a": "b"}]'
            return response(200, content, headers, None, 5, request)

        @urlmatch(
            scheme="http",
            netloc="localhost",
            path="/api/v4/tests",
            method="get",
            query=r".*page=2",
        )
        def resp_2(url, request):
            headers = {
                "content-type": "application/json",
                "X-Page": 2,
                "X-Next-Page": 2,
                "X-Per-Page": 1,
                "X-Total-Pages": 2,
                "X-Total": 2,
            }
            content = '[{"c": "d"}]'
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_1):
            obj = self.gl.http_list("/tests", as_list=False)
            self.assertEqual(len(obj), 2)
            self.assertEqual(
                obj._next_url, "http://localhost/api/v4/tests?per_page=1&page=2"
            )
            self.assertEqual(obj.current_page, 1)
            self.assertEqual(obj.prev_page, None)
            self.assertEqual(obj.next_page, 2)
            self.assertEqual(obj.per_page, 1)
            self.assertEqual(obj.total_pages, 2)
            self.assertEqual(obj.total, 2)

            with HTTMock(resp_2):
                l = list(obj)
                self.assertEqual(len(l), 2)
                self.assertEqual(l[0]["a"], "b")
                self.assertEqual(l[1]["c"], "d")


class TestGitlabHttpMethods(unittest.TestCase):
    def setUp(self):
        self.gl = Gitlab(
            "http://localhost", private_token="private_token", api_version=4
        )

    def test_build_url(self):
        r = self.gl._build_url("http://localhost/api/v4")
        self.assertEqual(r, "http://localhost/api/v4")
        r = self.gl._build_url("https://localhost/api/v4")
        self.assertEqual(r, "https://localhost/api/v4")
        r = self.gl._build_url("/projects")
        self.assertEqual(r, "http://localhost/api/v4/projects")

    def test_http_request(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects", method="get"
        )
        def resp_cont(url, request):
            headers = {"content-type": "application/json"}
            content = '[{"name": "project1"}]'
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_cont):
            http_r = self.gl.http_request("get", "/projects")
            http_r.json()
            self.assertEqual(http_r.status_code, 200)

    def test_http_request_404(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/not_there", method="get"
        )
        def resp_cont(url, request):
            content = {"Here is wh it failed"}
            return response(404, content, {}, None, 5, request)

        with HTTMock(resp_cont):
            self.assertRaises(
                GitlabHttpError, self.gl.http_request, "get", "/not_there"
            )

    def test_get_request(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects", method="get"
        )
        def resp_cont(url, request):
            headers = {"content-type": "application/json"}
            content = '{"name": "project1"}'
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_cont):
            result = self.gl.http_get("/projects")
            self.assertIsInstance(result, dict)
            self.assertEqual(result["name"], "project1")

    def test_get_request_raw(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects", method="get"
        )
        def resp_cont(url, request):
            headers = {"content-type": "application/octet-stream"}
            content = "content"
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_cont):
            result = self.gl.http_get("/projects")
            self.assertEqual(result.content.decode("utf-8"), "content")

    def test_get_request_404(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/not_there", method="get"
        )
        def resp_cont(url, request):
            content = {"Here is wh it failed"}
            return response(404, content, {}, None, 5, request)

        with HTTMock(resp_cont):
            self.assertRaises(GitlabHttpError, self.gl.http_get, "/not_there")

    def test_get_request_invalid_data(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects", method="get"
        )
        def resp_cont(url, request):
            headers = {"content-type": "application/json"}
            content = '["name": "project1"]'
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_cont):
            self.assertRaises(GitlabParsingError, self.gl.http_get, "/projects")

    def test_list_request(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects", method="get"
        )
        def resp_cont(url, request):
            headers = {"content-type": "application/json", "X-Total": 1}
            content = '[{"name": "project1"}]'
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_cont):
            result = self.gl.http_list("/projects", as_list=True)
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 1)

        with HTTMock(resp_cont):
            result = self.gl.http_list("/projects", as_list=False)
            self.assertIsInstance(result, GitlabList)
            self.assertEqual(len(result), 1)

        with HTTMock(resp_cont):
            result = self.gl.http_list("/projects", all=True)
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 1)

    def test_list_request_404(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/not_there", method="get"
        )
        def resp_cont(url, request):
            content = {"Here is why it failed"}
            return response(404, content, {}, None, 5, request)

        with HTTMock(resp_cont):
            self.assertRaises(GitlabHttpError, self.gl.http_list, "/not_there")

    def test_list_request_invalid_data(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects", method="get"
        )
        def resp_cont(url, request):
            headers = {"content-type": "application/json"}
            content = '["name": "project1"]'
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_cont):
            self.assertRaises(GitlabParsingError, self.gl.http_list, "/projects")

    def test_post_request(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects", method="post"
        )
        def resp_cont(url, request):
            headers = {"content-type": "application/json"}
            content = '{"name": "project1"}'
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_cont):
            result = self.gl.http_post("/projects")
            self.assertIsInstance(result, dict)
            self.assertEqual(result["name"], "project1")

    def test_post_request_404(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/not_there", method="post"
        )
        def resp_cont(url, request):
            content = {"Here is wh it failed"}
            return response(404, content, {}, None, 5, request)

        with HTTMock(resp_cont):
            self.assertRaises(GitlabHttpError, self.gl.http_post, "/not_there")

    def test_post_request_invalid_data(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects", method="post"
        )
        def resp_cont(url, request):
            headers = {"content-type": "application/json"}
            content = '["name": "project1"]'
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_cont):
            self.assertRaises(GitlabParsingError, self.gl.http_post, "/projects")

    def test_put_request(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects", method="put"
        )
        def resp_cont(url, request):
            headers = {"content-type": "application/json"}
            content = '{"name": "project1"}'
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_cont):
            result = self.gl.http_put("/projects")
            self.assertIsInstance(result, dict)
            self.assertEqual(result["name"], "project1")

    def test_put_request_404(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/not_there", method="put"
        )
        def resp_cont(url, request):
            content = {"Here is wh it failed"}
            return response(404, content, {}, None, 5, request)

        with HTTMock(resp_cont):
            self.assertRaises(GitlabHttpError, self.gl.http_put, "/not_there")

    def test_put_request_invalid_data(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects", method="put"
        )
        def resp_cont(url, request):
            headers = {"content-type": "application/json"}
            content = '["name": "project1"]'
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_cont):
            self.assertRaises(GitlabParsingError, self.gl.http_put, "/projects")

    def test_delete_request(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects", method="delete"
        )
        def resp_cont(url, request):
            headers = {"content-type": "application/json"}
            content = "true"
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_cont):
            result = self.gl.http_delete("/projects")
            self.assertIsInstance(result, requests.Response)
            self.assertEqual(result.json(), True)

    def test_delete_request_404(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/not_there", method="delete"
        )
        def resp_cont(url, request):
            content = {"Here is wh it failed"}
            return response(404, content, {}, None, 5, request)

        with HTTMock(resp_cont):
            self.assertRaises(GitlabHttpError, self.gl.http_delete, "/not_there")


class TestGitlabAuth(unittest.TestCase):
    def test_invalid_auth_args(self):
        self.assertRaises(
            ValueError,
            Gitlab,
            "http://localhost",
            api_version="4",
            private_token="private_token",
            oauth_token="bearer",
        )
        self.assertRaises(
            ValueError,
            Gitlab,
            "http://localhost",
            api_version="4",
            oauth_token="bearer",
            http_username="foo",
            http_password="bar",
        )
        self.assertRaises(
            ValueError,
            Gitlab,
            "http://localhost",
            api_version="4",
            private_token="private_token",
            http_password="bar",
        )
        self.assertRaises(
            ValueError,
            Gitlab,
            "http://localhost",
            api_version="4",
            private_token="private_token",
            http_username="foo",
        )

    def test_private_token_auth(self):
        gl = Gitlab("http://localhost", private_token="private_token", api_version="4")
        self.assertEqual(gl.private_token, "private_token")
        self.assertEqual(gl.oauth_token, None)
        self.assertEqual(gl.job_token, None)
        self.assertEqual(gl._http_auth, None)
        self.assertNotIn("Authorization", gl.headers)
        self.assertEqual(gl.headers["PRIVATE-TOKEN"], "private_token")
        self.assertNotIn("JOB-TOKEN", gl.headers)

    def test_oauth_token_auth(self):
        gl = Gitlab("http://localhost", oauth_token="oauth_token", api_version="4")
        self.assertEqual(gl.private_token, None)
        self.assertEqual(gl.oauth_token, "oauth_token")
        self.assertEqual(gl.job_token, None)
        self.assertEqual(gl._http_auth, None)
        self.assertEqual(gl.headers["Authorization"], "Bearer oauth_token")
        self.assertNotIn("PRIVATE-TOKEN", gl.headers)
        self.assertNotIn("JOB-TOKEN", gl.headers)

    def test_job_token_auth(self):
        gl = Gitlab("http://localhost", job_token="CI_JOB_TOKEN", api_version="4")
        self.assertEqual(gl.private_token, None)
        self.assertEqual(gl.oauth_token, None)
        self.assertEqual(gl.job_token, "CI_JOB_TOKEN")
        self.assertEqual(gl._http_auth, None)
        self.assertNotIn("Authorization", gl.headers)
        self.assertNotIn("PRIVATE-TOKEN", gl.headers)
        self.assertEqual(gl.headers["JOB-TOKEN"], "CI_JOB_TOKEN")

    def test_http_auth(self):
        gl = Gitlab(
            "http://localhost",
            private_token="private_token",
            http_username="foo",
            http_password="bar",
            api_version="4",
        )
        self.assertEqual(gl.private_token, "private_token")
        self.assertEqual(gl.oauth_token, None)
        self.assertEqual(gl.job_token, None)
        self.assertIsInstance(gl._http_auth, requests.auth.HTTPBasicAuth)
        self.assertEqual(gl.headers["PRIVATE-TOKEN"], "private_token")
        self.assertNotIn("Authorization", gl.headers)


class TestGitlab(unittest.TestCase):
    def setUp(self):
        self.gl = Gitlab(
            "http://localhost",
            private_token="private_token",
            ssl_verify=True,
            api_version=4,
        )

    def test_pickability(self):
        original_gl_objects = self.gl._objects
        pickled = pickle.dumps(self.gl)
        unpickled = pickle.loads(pickled)
        self.assertIsInstance(unpickled, Gitlab)
        self.assertTrue(hasattr(unpickled, "_objects"))
        self.assertEqual(unpickled._objects, original_gl_objects)

    def test_token_auth(self, callback=None):
        name = "username"
        id_ = 1

        @urlmatch(scheme="http", netloc="localhost", path="/api/v4/user", method="get")
        def resp_cont(url, request):
            headers = {"content-type": "application/json"}
            content = '{{"id": {0:d}, "username": "{1:s}"}}'.format(id_, name).encode(
                "utf-8"
            )
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_cont):
            self.gl.auth()
        self.assertEqual(self.gl.user.username, name)
        self.assertEqual(self.gl.user.id, id_)
        self.assertIsInstance(self.gl.user, CurrentUser)

    def test_hooks(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/hooks/1", method="get"
        )
        def resp_get_hook(url, request):
            headers = {"content-type": "application/json"}
            content = '{"url": "testurl", "id": 1}'.encode("utf-8")
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_get_hook):
            data = self.gl.hooks.get(1)
            self.assertIsInstance(data, Hook)
            self.assertEqual(data.url, "testurl")
            self.assertEqual(data.id, 1)

    def test_projects(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects/1", method="get"
        )
        def resp_get_project(url, request):
            headers = {"content-type": "application/json"}
            content = '{"name": "name", "id": 1}'.encode("utf-8")
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_get_project):
            data = self.gl.projects.get(1)
            self.assertIsInstance(data, Project)
            self.assertEqual(data.name, "name")
            self.assertEqual(data.id, 1)

    def test_project_environments(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects/1$", method="get"
        )
        def resp_get_project(url, request):
            headers = {"content-type": "application/json"}
            content = '{"name": "name", "id": 1}'.encode("utf-8")
            return response(200, content, headers, None, 5, request)

        @urlmatch(
            scheme="http",
            netloc="localhost",
            path="/api/v4/projects/1/environments/1",
            method="get",
        )
        def resp_get_environment(url, request):
            headers = {"content-type": "application/json"}
            content = '{"name": "environment_name", "id": 1, "last_deployment": "sometime"}'.encode(
                "utf-8"
            )
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_get_project, resp_get_environment):
            project = self.gl.projects.get(1)
            environment = project.environments.get(1)
            self.assertIsInstance(environment, ProjectEnvironment)
            self.assertEqual(environment.id, 1)
            self.assertEqual(environment.last_deployment, "sometime")
            self.assertEqual(environment.name, "environment_name")

    def test_groups(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/groups/1", method="get"
        )
        def resp_get_group(url, request):
            headers = {"content-type": "application/json"}
            content = '{"name": "name", "id": 1, "path": "path"}'
            content = content.encode("utf-8")
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_get_group):
            data = self.gl.groups.get(1)
            self.assertIsInstance(data, Group)
            self.assertEqual(data.name, "name")
            self.assertEqual(data.path, "path")
            self.assertEqual(data.id, 1)

    def test_issues(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/issues", method="get"
        )
        def resp_get_issue(url, request):
            headers = {"content-type": "application/json"}
            content = '[{"name": "name", "id": 1}, ' '{"name": "other_name", "id": 2}]'
            content = content.encode("utf-8")
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_get_issue):
            data = self.gl.issues.list()
            self.assertEqual(data[1].id, 2)
            self.assertEqual(data[1].name, "other_name")

    @urlmatch(scheme="http", netloc="localhost", path="/api/v4/users/1", method="get")
    def resp_get_user(self, url, request):
        headers = {"content-type": "application/json"}
        content = (
            '{"name": "name", "id": 1, "password": "password", '
            '"username": "username", "email": "email"}'
        )
        content = content.encode("utf-8")
        return response(200, content, headers, None, 5, request)

    def test_users(self):
        with HTTMock(self.resp_get_user):
            user = self.gl.users.get(1)
            self.assertIsInstance(user, User)
            self.assertEqual(user.name, "name")
            self.assertEqual(user.id, 1)

    def test_user_status(self):
        @urlmatch(
            scheme="http",
            netloc="localhost",
            path="/api/v4/users/1/status",
            method="get",
        )
        def resp_get_user_status(url, request):
            headers = {"content-type": "application/json"}
            content = '{"message": "test", "message_html": "<h1>Message</h1>", "emoji": "thumbsup"}'
            content = content.encode("utf-8")
            return response(200, content, headers, None, 5, request)

        with HTTMock(self.resp_get_user):
            user = self.gl.users.get(1)
        with HTTMock(resp_get_user_status):
            status = user.status.get()
            self.assertIsInstance(status, UserStatus)
            self.assertEqual(status.message, "test")
            self.assertEqual(status.emoji, "thumbsup")

    def test_todo(self):
        with open(os.path.dirname(__file__) + "/data/todo.json", "r") as json_file:
            todo_content = json_file.read()
            json_content = json.loads(todo_content)
            encoded_content = todo_content.encode("utf-8")

        @urlmatch(scheme="http", netloc="localhost", path="/api/v4/todos", method="get")
        def resp_get_todo(url, request):
            headers = {"content-type": "application/json"}
            return response(200, encoded_content, headers, None, 5, request)

        @urlmatch(
            scheme="http",
            netloc="localhost",
            path="/api/v4/todos/102/mark_as_done",
            method="post",
        )
        def resp_mark_as_done(url, request):
            headers = {"content-type": "application/json"}
            single_todo = json.dumps(json_content[0])
            content = single_todo.encode("utf-8")
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_get_todo):
            todo = self.gl.todos.list()[0]
            self.assertIsInstance(todo, Todo)
            self.assertEqual(todo.id, 102)
            self.assertEqual(todo.target_type, "MergeRequest")
            self.assertEqual(todo.target["assignee"]["username"], "root")
            with HTTMock(resp_mark_as_done):
                todo.mark_as_done()

    def test_todo_mark_all_as_done(self):
        @urlmatch(
            scheme="http",
            netloc="localhost",
            path="/api/v4/todos/mark_as_done",
            method="post",
        )
        def resp_mark_all_as_done(url, request):
            headers = {"content-type": "application/json"}
            return response(204, {}, headers, None, 5, request)

        with HTTMock(resp_mark_all_as_done):
            self.gl.todos.mark_all_as_done()

    def test_deployment(self):
        content = '{"id": 42, "status": "success", "ref": "master"}'
        json_content = json.loads(content)

        @urlmatch(
            scheme="http",
            netloc="localhost",
            path="/api/v4/projects/1/deployments",
            method="post",
        )
        def resp_deployment_create(url, request):
            headers = {"content-type": "application/json"}
            return response(200, json_content, headers, None, 5, request)

        @urlmatch(
            scheme="http",
            netloc="localhost",
            path="/api/v4/projects/1/deployments/42",
            method="put",
        )
        def resp_deployment_update(url, request):
            headers = {"content-type": "application/json"}
            return response(200, json_content, headers, None, 5, request)

        with HTTMock(resp_deployment_create):
            deployment = self.gl.projects.get(1, lazy=True).deployments.create(
                {
                    "environment": "Test",
                    "sha": "1agf4gs",
                    "ref": "master",
                    "tag": False,
                    "status": "created",
                }
            )
            self.assertEqual(deployment.id, 42)
            self.assertEqual(deployment.status, "success")
            self.assertEqual(deployment.ref, "master")

        with HTTMock(resp_deployment_update):
            json_content["status"] = "failed"
            deployment.status = "failed"
            deployment.save()
            self.assertEqual(deployment.status, "failed")

    def test_user_activate_deactivate(self):
        @urlmatch(
            scheme="http",
            netloc="localhost",
            path="/api/v4/users/1/activate",
            method="post",
        )
        def resp_activate(url, request):
            headers = {"content-type": "application/json"}
            return response(201, {}, headers, None, 5, request)

        @urlmatch(
            scheme="http",
            netloc="localhost",
            path="/api/v4/users/1/deactivate",
            method="post",
        )
        def resp_deactivate(url, request):
            headers = {"content-type": "application/json"}
            return response(201, {}, headers, None, 5, request)

        with HTTMock(resp_activate), HTTMock(resp_deactivate):
            self.gl.users.get(1, lazy=True).activate()
            self.gl.users.get(1, lazy=True).deactivate()

    def test_update_submodule(self):
        @urlmatch(
            scheme="http", netloc="localhost", path="/api/v4/projects/1$", method="get"
        )
        def resp_get_project(url, request):
            headers = {"content-type": "application/json"}
            content = '{"name": "name", "id": 1}'.encode("utf-8")
            return response(200, content, headers, None, 5, request)

        @urlmatch(
            scheme="http",
            netloc="localhost",
            path="/api/v4/projects/1/repository/submodules/foo%2Fbar",
            method="put",
        )
        def resp_update_submodule(url, request):
            headers = {"content-type": "application/json"}
            content = """{
            "id": "ed899a2f4b50b4370feeea94676502b42383c746",
            "short_id": "ed899a2f4b5",
            "title": "Message",
            "author_name": "Author",
            "author_email": "author@example.com",
            "committer_name": "Author",
            "committer_email": "author@example.com",
            "created_at": "2018-09-20T09:26:24.000-07:00",
            "message": "Message",
            "parent_ids": [ "ae1d9fb46aa2b07ee9836d49862ec4e2c46fbbba" ],
            "committed_date": "2018-09-20T09:26:24.000-07:00",
            "authored_date": "2018-09-20T09:26:24.000-07:00",
            "status": null}"""
            content = content.encode("utf-8")
            return response(200, content, headers, None, 5, request)

        with HTTMock(resp_get_project):
            project = self.gl.projects.get(1)
            self.assertIsInstance(project, Project)
            self.assertEqual(project.name, "name")
            self.assertEqual(project.id, 1)
        with HTTMock(resp_update_submodule):
            ret = project.update_submodule(
                submodule="foo/bar",
                branch="master",
                commit_sha="4c3674f66071e30b3311dac9b9ccc90502a72664",
                commit_message="Message",
            )
            self.assertIsInstance(ret, dict)
            self.assertEqual(ret["message"], "Message")
            self.assertEqual(ret["id"], "ed899a2f4b50b4370feeea94676502b42383c746")

    def _default_config(self):
        fd, temp_path = tempfile.mkstemp()
        os.write(fd, valid_config)
        os.close(fd)
        return temp_path

    def test_from_config(self):
        config_path = self._default_config()
        gitlab.Gitlab.from_config("one", [config_path])
        os.unlink(config_path)

    def test_subclass_from_config(self):
        class MyGitlab(gitlab.Gitlab):
            pass

        config_path = self._default_config()
        gl = MyGitlab.from_config("one", [config_path])
        self.assertIsInstance(gl, MyGitlab)
        os.unlink(config_path)


class TestRetryWaitTime(unittest.TestCase):
    def setUp(self):
        self.session_mock = unittest.mock.Mock(name="Session mock")
        self.session_mock.prepare_request.return_value.url = "http://localhost"
        self.session_mock.merge_environment_settings.return_value = {}

    @unittest.mock.patch("gitlab.time.sleep", name="sleep mock")
    def test_default_retry_wait_time(self, sleep_mock):
        self.gl = Gitlab(
            "http://localhost",
            private_token="private_token",
            ssl_verify=True,
            api_version=4,
            session=self.session_mock,
        )

        self.session_mock.send.side_effect = [
            response(429, headers={"Retry-After": "60"}),
            response(429, headers={"Retry-After": "180"}),
            response(429),
            response(429),
            response(200),
        ]

        http_r = self.gl.http_request("get", "/projects", max_retries=4)

        self.assertEqual(http_r.status_code, 200)

        self.assertEqual(
            [
                unittest.mock.call(60),
                unittest.mock.call(180),
                unittest.mock.call(unittest.mock.ANY),
                unittest.mock.call(unittest.mock.ANY),
            ],
            sleep_mock.call_args_list,
        )

        self.assertAlmostEqual(
            sleep_mock.call_args_list[2][0][0], 2 ** 2 * 0.1,
        )

        self.assertAlmostEqual(
            sleep_mock.call_args_list[3][0][0], 2 ** 3 * 0.1,
        )

    @unittest.mock.patch("gitlab.time.sleep", name="sleep mock")
    def test_custom_retry_wait_time(self, sleep_mock):
        self.gl = Gitlab(
            "http://localhost",
            private_token="private_token",
            ssl_verify=True,
            api_version=4,
            session=self.session_mock,
            get_wait_time=unittest.mock.Mock(side_effect=[100, 200]),
        )

        self.session_mock.send.side_effect = [
            response(429, headers={"Retry-After": "60"}),
            response(429),
            response(200),
        ]

        http_r = self.gl.http_request("get", "/projects", max_retries=2)

        self.assertEqual(http_r.status_code, 200)

        self.assertEqual(
            [unittest.mock.call(100), unittest.mock.call(200),],
            sleep_mock.call_args_list,
        )


class TestRequestThrottler(unittest.TestCase):
    def setUp(self):
        self.throttler = gitlab.RequestThrottler(5, 10)

        monotonic_patcher = unittest.mock.patch(
            "gitlab.time.monotonic", name="monotonic mock", return_value=0,
        )
        self.monotonic_mock = monotonic_patcher.start()
        self.addCleanup(monotonic_patcher.stop)

        sleep_patcher = unittest.mock.patch(
            "gitlab.time.sleep", name="sleep mock", side_effect=self._sleep,
        )
        self.sleep_mock = sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    def _sleep(self, sleep_time):
        self.monotonic_mock.return_value += sleep_time

    def test_throttling(self):
        for _ in range(0, 5):
            self.monotonic_mock.return_value += 1
            self.throttler()

        self.assertFalse(self.sleep_mock.called)
        self.assertEqual([1, 2, 3, 4, 5], self.throttler.calls_within_period)

        self.monotonic_mock.return_value += 1
        self.assertEqual(self.monotonic_mock.return_value, 6)
        self.throttler()

        self.sleep_mock.assert_called_once_with(6)
        self.assertEqual(self.monotonic_mock.return_value, 12)

        self.assertEqual([2, 3, 4, 5, 12], self.throttler.calls_within_period)

        self.sleep_mock.reset_mock()

        self.monotonic_mock.return_value += 1
        self.throttler()
        self.assertFalse(self.sleep_mock.called)
        self.assertEqual([3, 4, 5, 12, 13], self.throttler.calls_within_period)

        self.monotonic_mock.return_value = 100
        self.throttler()
        self.assertFalse(self.sleep_mock.called)
        self.assertEqual([100], self.throttler.calls_within_period)
