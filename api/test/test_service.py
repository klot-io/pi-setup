import unittest
import unittest.mock

import os
import yaml
import pykube.exceptions

import service


class TestService(unittest.TestCase):

    maxDiff = None

    @unittest.mock.patch("pykube.HTTPClient", unittest.mock.MagicMock)
    @unittest.mock.patch("pykube.KubeConfig.from_service_account", unittest.mock.MagicMock)
    def setUp(self):

        self.app = service.app()
        self.api = self.app.test_client()

    @unittest.mock.patch("pykube.HTTPClient")
    @unittest.mock.patch("pykube.KubeConfig.from_service_account")
    def test_app(self, mock_account, mock_client):

        mock_account.return_value = "service"
        mock_client.return_value = "borg"

        app = service.app()

        self.assertEqual(app.kube, "borg")
        mock_client.assert_called_once_with("service")

    def test_health(self):

        self.assertEqual(self.api.get("/health").json, {"message": "OK"})

    @unittest.mock.patch("pykube.Node.objects")
    def test_Node(self, mock_node):

        master = unittest.mock.MagicMock()
        worker = unittest.mock.MagicMock()
        match = unittest.mock.MagicMock()

        master.obj = {
            "metadata": {
                "name": "people",
                "labels": {
                    "node-role.kubernetes.io/master": "true"
                }
            }
        }
        worker.obj = {
            "metadata": {
                "name": "stuff"
            }
        }
        match.obj = {
            "metadata": {
                "name": "things",
                "labels": {
                    "fancy/mark": "stain"
                }
            }
        }

        mock_node.return_value.filter.return_value = [match, master, worker]

        self.assertEqual(self.api.options("/node").json, {
            "options": [
                "people",
                "stuff",
                "things"
            ]
        })

        mock_node.assert_called_once_with(self.app.kube)

        self.assertEqual(self.api.options("/node?app=fancy&label=mark&value=stain").json, {
            "options": [
                "things"
            ]
        })

    @unittest.mock.patch("pykube.KlotIOApp.objects")
    @unittest.mock.patch("service.os.path.exists")
    @unittest.mock.patch("service.open", create=True)
    def test_Member(self, mock_open, mock_exists, mock_app):

        mock_exists.return_value = True

        mock_open.side_effect = [
            unittest.mock.mock_open(read_data=yaml.safe_dump({"cluster": "unittest"})).return_value
        ]

        people = unittest.mock.MagicMock()
        stuff = unittest.mock.MagicMock()
        things = unittest.mock.MagicMock()

        people.obj = {
            "metadata": {
                "name": "people",
            },
            "spec" : {
                "group": "us",
                "member": "People"
            },
            "url": "app"
        }
        stuff.obj = {
            "metadata": {
                "name": "stuff"
            },
            "spec" : {
                "group": "them",
                "member": "Stuff"
            },
            "url": "dot"
        }
        things.obj = {
            "metadata": {
                "name": "things",
            },
            "spec" : {
                "group": "us",
                "member": "Things"
            },
            "url": "com"
        }

        mock_lookup = unittest.mock.MagicMock()
        mock_lookup.get.return_value = people

        mock_app.return_value.filter.side_effect = [mock_lookup, [things, people, stuff], pykube.exceptions.ObjectDoesNotExist()]

        self.assertEqual(self.api.get("/app/people/member").json, {
            "members": [
                {
                    "name": "Things",
                    "url": "com"
                },
                {
                    "name": "Klot I/O",
                    "url": "http://unittest-klot-io.local"
                }
            ]
        })

        mock_app.assert_called_with(self.app.kube)

        mock_lookup.get.assert_called_once_with(name="people")

        mock_exists.assert_called_once_with("/opt/klot-io/config/kubernetes.yaml")

        mock_open.assert_called_once_with("/opt/klot-io/config/kubernetes.yaml", "r")

        response = self.api.get("/app/nope/member")

        self.assertEqual(response.json, {
            "message": "nope not found"
        })

        self.assertEqual(response.status_code, 404)
