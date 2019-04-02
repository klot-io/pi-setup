import os
import time
import socket
import paramiko

import warnings
import cryptography
import cryptography.utils
with warnings.catch_warnings():
    warnings.simplefilter('ignore', cryptography.utils.CryptographyDeprecationWarning)
    import cryptography.hazmat.primitives.constant_time

class Deploy:

    BASE = "/opt/klot-io"

    def __init__(self, node, password):

        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh_client.connect(hostname=socket.gethostbyname(node), username="pi", password=password)
        self.sftp_client = self.ssh_client.open_sftp()

    def execute(self, command):

        print(command)
        stdin, stdout, stderr = self.ssh_client.exec_command(command)

        for stdout_line in stdout:
            print(stdout_line.encode('ascii', 'ignore').decode('ascii').rstrip())

    def put(self, source):

        print (f"{source} -> {self.BASE}/{source}")

        if os.path.isfile(source):
            self.sftp_client.put(source, f"{self.BASE}/{source}")
        else:
            for path in os.listdir(source):
                self.put(f"{source}/{path}")

    def update(self, service, source):

        self.put(source)
        self.execute(f"sudo systemctl restart {service}")

    def close(self):

        self.sftp_client.close()
        self.ssh_client.close()
